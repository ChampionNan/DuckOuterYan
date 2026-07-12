//===----------------------------------------------------------------------===//
// PhysicalSJBuild — OuterYan semi-join build operator.
//
// IMPLEMENTATION REFERENCES — please cross-check against these when editing.
//
// Primary references (Sink + Source dual role, child meta-pipeline pattern):
//   - embryo-labs/dynamic-predicate-transfer:
//       src/execution/operator/persistent/physical_create_bf.cpp
//     The Sink/Combine/Finalize/Source layout + BuildPipelines +
//     BuildPipelinesFromRelated come directly from this file's structure.
//     (Local /tmp/dpt_physical_create_bf.cpp during the design session.)
//   - embryo-labs/Robust-Predicate-Transfer:
//       src/execution/operator/persistent/physical_create_bf.cpp
//     Older variant; same shape, fewer runtime-optimisation knobs.
//
// What we INTENTIONALLY DO NOT carry over from DPT (per plan 3 non-goals):
//   - GiveUpBFCreation runtime selectivity / OOM guards
//   - is_successful / can_stop mutable flags
//   - min_max_to_create / DynamicTableFilterSet pushdown
//   - TemporaryMemoryManager registration (deferred — open question 3)
//   - Parallel finalize event (single-threaded loop over filters is fine
//     for v1; the parallel work is in the Sink stage)
//
// What we ADD vs DPT:
//   - Bitmap-first / HashFilter-fallback decision inside Finalize
//     (KeyBitmap::TryBuild → if nullptr fall back to HashFilter::Build).
//   - SemiJoinFilter carrier (instead of BloomFilter / HashFilter).
//
// DuckDB-side patterns referenced:
//   - PhysicalRecursiveCTE / PhysicalColumnDataScan — Sink+Source operators
//     that buffer and re-emit (we follow the same ColumnDataCollection idiom).
//   - PhysicalHashJoin — for build-side data materialisation patterns.
//===----------------------------------------------------------------------===//

#include "duckdb/execution/operator/join/physical_sj_build.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/common/types/column/column_data_collection.hpp"
#include "duckdb/main/client_config.hpp"
#include "duckdb/main/client_context.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/hash_filter.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/key_bitmap.hpp"
#include "duckdb/parallel/base_pipeline_event.hpp"
#include "duckdb/parallel/executor_task.hpp"
#include "duckdb/parallel/meta_pipeline.hpp"
#include "duckdb/parallel/pipeline.hpp"
#include "duckdb/parallel/thread_context.hpp"
#include "duckdb/planner/operator/logical_sj_build.hpp"

#include <cctype>
#include <mutex>

namespace duckdb {

// Per-session budget knob. Set via:
//   SET VARIABLE outer_yan_bitmap_max_bytes = 17179869184;
// Read from ClientConfig::user_variables (DuckDB's case-insensitive map
// populated by SET VARIABLE) rather than registering a global
// ConfigurationOption — the latter would require touching generated
// settings infrastructure (settings.hpp / settings.cpp / config.cpp's
// internal_options table) and is out of scope for plan 3. Setting to 0
// forces the HashFilter fallback for all SemiJoinFilters in the session
// (escape hatch for benchmarks).
idx_t PhysicalSJBuild::GetBitmapBudget(ClientContext &context) {
	auto &cfg = ClientConfig::GetConfig(context);
	auto it = cfg.user_variables.find(kBitmapBudgetVar);
	if (it == cfg.user_variables.end() || it->second.IsNull()) {
		return kDefaultBitmapBudgetBytes;
	}
	try {
		auto v = it->second.DefaultCastAs(LogicalType::UBIGINT);
		return NumericCast<idx_t>(v.GetValue<uint64_t>());
	} catch (...) {
		throw InvalidInputException("SET VARIABLE %s must be a non-negative integer (got %s)", kBitmapBudgetVar,
		                            it->second.ToString());
	}
}

// Per-session selector for the HashFilter hash function used when a filter
// falls back from KeyBitmap. The default routes to HashKeyDuckDB
// (CombineHash); "murmur" remains available for A/B comparison.
HashFilter::HashKind PhysicalSJBuild::GetHashKind(ClientContext &context) {
	auto &cfg = ClientConfig::GetConfig(context);
	auto it = cfg.user_variables.find(kHashFnVar);
	if (it == cfg.user_variables.end() || it->second.IsNull()) {
		return HashFilter::HashKind::DUCKDB_COMBINE;
	}
	string raw;
	try {
		raw = it->second.DefaultCastAs(LogicalType::VARCHAR).GetValue<string>();
	} catch (...) {
		throw InvalidInputException("SET VARIABLE %s must be a string ('murmur' or 'duckdb') — got %s", kHashFnVar,
		                            it->second.ToString());
	}
	string lower;
	lower.reserve(raw.size());
	for (auto c : raw) {
		lower.push_back(static_cast<char>(std::tolower(static_cast<unsigned char>(c))));
	}
	if (lower == "murmur" || lower == "murmur_hash2") {
		return HashFilter::HashKind::MURMUR_HASH2;
	}
	if (lower == "duckdb" || lower == "duckdb_combine" || lower == "combine") {
		return HashFilter::HashKind::DUCKDB_COMBINE;
	}
	throw InvalidInputException("SET VARIABLE %s: unknown value '%s' (expected 'murmur' or 'duckdb')", kHashFnVar, raw);
}

PhysicalSJBuild::PhysicalSJBuild(PhysicalPlan &physical_plan, vector<LogicalType> types,
                                 vector<shared_ptr<SemiJoinFilter>> sj_to_create_p,
                                 vector<vector<idx_t>> build_col_ids_per_filter_p,
                                 idx_t estimated_cardinality, bool top_down_p)
    : PhysicalOperator(physical_plan, PhysicalOperatorType::SJ_BUILD, std::move(types), estimated_cardinality),
      sj_to_create(std::move(sj_to_create_p)),
      build_col_ids_per_filter(std::move(build_col_ids_per_filter_p)), top_down(top_down_p) {
	if (sj_to_create.size() != build_col_ids_per_filter.size()) {
		throw InternalException("PhysicalSJBuild: filter / build_col_ids count mismatch");
	}
}

string PhysicalSJBuild::GetName() const {
	return top_down ? "SJ_BUILD_ROUND_2" : "SJ_BUILD_ROUND_1";
}

// ===========================================================================
// Sink — materialise build-side data into a global ColumnDataCollection.
//
// Reference: DPT physical_create_bf.cpp `CreateBFGlobalSinkState` +
// `CreateBFLocalSinkState`. Same pattern: per-thread local
// ColumnDataCollection, folded into a global at Combine/Finalize. Differs
// only in that we don't carry `temporary_memory_state`, `min_max` aggregates,
// or `is_successful` (all non-goals per plan 3).
// ===========================================================================

class SJBuildGlobalSinkState : public GlobalSinkState {
public:
	SJBuildGlobalSinkState(ClientContext &context, const PhysicalSJBuild &op) : context(context), op(op) {
		total_data = make_uniq<ColumnDataCollection>(context, op.types);
	}

	ClientContext &context;
	const PhysicalSJBuild &op;

	// Lock for fold-in at Combine time; nothing else contends on this.
	std::mutex glock;
	// Per-thread local collections. Moved into total_data at Finalize.
	vector<unique_ptr<ColumnDataCollection>> local_data_collections;
	// Final merged collection — both the Sink output and the Source input.
	unique_ptr<ColumnDataCollection> total_data;
};

class SJBuildLocalSinkState : public LocalSinkState {
public:
	SJBuildLocalSinkState(ClientContext &context, const PhysicalSJBuild &op) {
		local_data = make_uniq<ColumnDataCollection>(context, op.types);
	}

	unique_ptr<ColumnDataCollection> local_data;
};

unique_ptr<GlobalSinkState> PhysicalSJBuild::GetGlobalSinkState(ClientContext &context) const {
	return make_uniq<SJBuildGlobalSinkState>(context, *this);
}

unique_ptr<LocalSinkState> PhysicalSJBuild::GetLocalSinkState(ExecutionContext &context) const {
	return make_uniq<SJBuildLocalSinkState>(context.client, *this);
}

// Reference: DPT physical_create_bf.cpp `PhysicalCreateBF::Sink` (line ~262).
// Simplified — no GiveUpBFCreation, no min-max aggregation.
SinkResultType PhysicalSJBuild::Sink(ExecutionContext &context, DataChunk &chunk, OperatorSinkInput &input) const {
	(void)context;
	auto &lstate = input.local_state.Cast<SJBuildLocalSinkState>();
	lstate.local_data->Append(chunk);
	return SinkResultType::NEED_MORE_INPUT;
}

// Reference: DPT physical_create_bf.cpp `PhysicalCreateBF::Combine` (line ~283).
SinkCombineResultType PhysicalSJBuild::Combine(ExecutionContext &context, OperatorSinkCombineInput &input) const {
	(void)context;
	auto &gstate = input.global_state.Cast<SJBuildGlobalSinkState>();
	auto &lstate = input.local_state.Cast<SJBuildLocalSinkState>();
	std::lock_guard<std::mutex> lock(gstate.glock);
	gstate.local_data_collections.emplace_back(std::move(lstate.local_data));
	return SinkCombineResultType::FINISHED;
}

// =============================================================================
// Sequential HashFilter build — used for force_hash filters, ineligible
// types/composites, and as the in-FinishEvent fallback when the bitmap range
// exceeds the byte budget. Parallel HashFilter build is Stage 2 (deferred).
// =============================================================================
static void BuildOneFilterAsHash(ClientContext &context, const ColumnDataCollection &total_data,
                                 const shared_ptr<SemiJoinFilter> &filter, const vector<idx_t> &build_col_ids,
                                 HashFilter::HashKind hash_kind, const char *reason) {
	(void)context;
	auto hf = make_shared_ptr<HashFilter>(hash_kind);
	DataChunk scan_chunk;
	total_data.InitializeScanChunk(scan_chunk);
	ColumnDataScanState scan_state;
	total_data.InitializeScan(scan_state);
	while (total_data.Scan(scan_state, scan_chunk)) {
		hf->Build(scan_chunk, build_col_ids);
		scan_chunk.Reset();
	}
	hf->Finalize();
	filter->FinalizeAsHash(std::move(hf), reason);
}

// =============================================================================
// Within-filter parallel KeyBitmap build (Stage 1).
//
// Layout — mirrors HashJoinTableInitEvent → HashJoinFinalizeEvent:
//
//   SJBuildBitmapInitEvent
//     Schedule    : N SJBuildBitmapScanTask (parallel min/max over chunks)
//     FinishEvent : reduce → Allocate → dispatch FillEvent or hash fallback
//   SJBuildBitmapFillEvent
//     Schedule    : N SJBuildBitmapFillTask (parallel atomic-OR bit-set)
//     FinishEvent : FinalizePopCount → filter->FinalizeAsBitmap
//
// Each filter dispatches its own chain independently from Finalize. Across-
// filter and within-filter parallelism compose naturally — DuckDB's task
// scheduler load-balances on its own; no explicit thread-count knob.
// =============================================================================

//! Tasks-per-event chunking, matching HashJoinFinalizeEvent::CHUNKS_PER_TASK.
static constexpr idx_t SJ_BUILD_CHUNKS_PER_TASK = 64;

//! Per-filter scratch shared between SJBuildBitmapInitEvent and its dispatched
//! SJBuildBitmapFillEvent. `partials` is written by the init tasks (each task
//! writes its own slot, no contention); `bitmap` is published in the init
//! event's FinishEvent and read by all fill tasks.
struct SJBuildFilterScratch {
	vector<KeyBitmap::MinMaxRange> partials;
	unique_ptr<KeyBitmap> bitmap;
};

class SJBuildBitmapScanTask : public ExecutorTask {
public:
	SJBuildBitmapScanTask(shared_ptr<Event> event_p, ClientContext &context_p, const PhysicalSJBuild &op_p,
	                      SJBuildGlobalSinkState &gstate_p, shared_ptr<SJBuildFilterScratch> scratch_p, idx_t task_idx_p,
	                      idx_t chunk_from_p, idx_t chunk_to_p, idx_t col_id_p, LogicalTypeId type_id_p)
	    : ExecutorTask(context_p, std::move(event_p), op_p), gstate(gstate_p), scratch(std::move(scratch_p)),
	      task_idx(task_idx_p), chunk_from(chunk_from_p), chunk_to(chunk_to_p), col_id(col_id_p), type_id(type_id_p) {
	}

	TaskExecutionResult ExecuteTask(TaskExecutionMode mode) override {
		(void)mode;
		scratch->partials[task_idx] =
		    KeyBitmap::ScanMinMaxRange(*gstate.total_data, col_id, type_id, chunk_from, chunk_to);
		event->FinishTask();
		return TaskExecutionResult::TASK_FINISHED;
	}

	string TaskType() const override {
		return "SJBuildBitmapScanTask";
	}

private:
	SJBuildGlobalSinkState &gstate;
	shared_ptr<SJBuildFilterScratch> scratch;
	idx_t task_idx;
	idx_t chunk_from;
	idx_t chunk_to;
	idx_t col_id;
	LogicalTypeId type_id;
};

class SJBuildBitmapFillTask : public ExecutorTask {
public:
	SJBuildBitmapFillTask(shared_ptr<Event> event_p, ClientContext &context_p, const PhysicalSJBuild &op_p,
	                      SJBuildGlobalSinkState &gstate_p, shared_ptr<SJBuildFilterScratch> scratch_p,
	                      idx_t chunk_from_p, idx_t chunk_to_p, idx_t col_id_p, LogicalTypeId type_id_p)
	    : ExecutorTask(context_p, std::move(event_p), op_p), gstate(gstate_p), scratch(std::move(scratch_p)),
	      chunk_from(chunk_from_p), chunk_to(chunk_to_p), col_id(col_id_p), type_id(type_id_p) {
	}

	TaskExecutionResult ExecuteTask(TaskExecutionMode mode) override {
		(void)mode;
		scratch->bitmap->FillBitsRange<true>(*gstate.total_data, col_id, type_id, chunk_from, chunk_to);
		event->FinishTask();
		return TaskExecutionResult::TASK_FINISHED;
	}

	string TaskType() const override {
		return "SJBuildBitmapFillTask";
	}

private:
	SJBuildGlobalSinkState &gstate;
	shared_ptr<SJBuildFilterScratch> scratch;
	idx_t chunk_from;
	idx_t chunk_to;
	idx_t col_id;
	LogicalTypeId type_id;
};

//! Fill event declared before Init so the Init's FinishEvent body can name it.
class SJBuildBitmapFillEvent : public BasePipelineEvent {
public:
	SJBuildBitmapFillEvent(Pipeline &pipeline_p, ClientContext &context_p, const PhysicalSJBuild &op_p,
	                       SJBuildGlobalSinkState &gstate_p, idx_t filter_idx_p, idx_t col_id_p,
	                       LogicalTypeId type_id_p, shared_ptr<SJBuildFilterScratch> scratch_p)
	    : BasePipelineEvent(pipeline_p), context(context_p), op(op_p), gstate(gstate_p), filter_idx(filter_idx_p),
	      col_id(col_id_p), type_id(type_id_p), scratch(std::move(scratch_p)) {
	}

	void Schedule() override {
		const idx_t cc = gstate.total_data->ChunkCount();
		const idx_t num_tasks = MaxValue<idx_t>((cc + SJ_BUILD_CHUNKS_PER_TASK - 1) / SJ_BUILD_CHUNKS_PER_TASK, 1);
		vector<shared_ptr<Task>> tasks;
		tasks.reserve(num_tasks);
		for (idx_t t = 0; t < num_tasks; t++) {
			const idx_t cf = t * SJ_BUILD_CHUNKS_PER_TASK;
			const idx_t ct = MinValue<idx_t>(cf + SJ_BUILD_CHUNKS_PER_TASK, cc);
			tasks.push_back(make_uniq<SJBuildBitmapFillTask>(shared_from_this(), context, op, gstate, scratch, cf, ct,
			                                                 col_id, type_id));
		}
		SetTasks(std::move(tasks));
	}

	void FinishEvent() override {
		scratch->bitmap->FinalizePopCount();
		op.sj_to_create[filter_idx]->FinalizeAsBitmap(std::move(scratch->bitmap));
	}

private:
	ClientContext &context;
	const PhysicalSJBuild &op;
	SJBuildGlobalSinkState &gstate;
	idx_t filter_idx;
	idx_t col_id;
	LogicalTypeId type_id;
	shared_ptr<SJBuildFilterScratch> scratch;
};

// =============================================================================
// Parallel INLINE_64 HashFilter build (Stage 2).
//
// Single-phase event — Schedule both sizes the table and fans out the
// chunk-sharded insert tasks. The table is pre-sized for
// `total_data.Count() * 2`, so the load factor stays ≤ 0.5 and no thread
// ever has to resize while inserting. Atomic occupancy-bit fetch_or in
// HashFilter::InsertHashedKey64Templated<true> serialises slot claims, then
// the winning thread is the sole writer of the 16-byte InlineSlot.
//
// Dispatched from PhysicalSJBuild::Finalize for force_hash / non-bitmap-
// eligible / budget=0 filters when their key is INLINE_64-eligible, and
// from SJBuildBitmapInitEvent::FinishEvent on the bitmap-overflow path.
// BOXED-mode keys (varchar, decimal, composite) keep falling through to
// the sequential BuildOneFilterAsHash — Stage 3 work.
// =============================================================================
class SJBuildHashInsertTask : public ExecutorTask {
public:
	SJBuildHashInsertTask(shared_ptr<Event> event_p, ClientContext &context_p, const PhysicalSJBuild &op_p,
	                      SJBuildGlobalSinkState &gstate_p, shared_ptr<HashFilter> hf_p,
	                      const vector<idx_t> &build_col_ids_p, idx_t chunk_from_p, idx_t chunk_to_p)
	    : ExecutorTask(context_p, std::move(event_p), op_p), gstate(gstate_p), hf(std::move(hf_p)),
	      build_col_ids(build_col_ids_p), chunk_from(chunk_from_p), chunk_to(chunk_to_p) {
	}

	TaskExecutionResult ExecuteTask(TaskExecutionMode mode) override {
		(void)mode;
		DataChunk scan_chunk;
		gstate.total_data->InitializeScanChunk(scan_chunk);
		for (idx_t ci = chunk_from; ci < chunk_to; ci++) {
			scan_chunk.Reset();
			gstate.total_data->FetchChunk(ci, scan_chunk);
			hf->BuildChunkInline64<true>(scan_chunk, build_col_ids);
		}
		event->FinishTask();
		return TaskExecutionResult::TASK_FINISHED;
	}

	string TaskType() const override {
		return "SJBuildHashInsertTask";
	}

private:
	SJBuildGlobalSinkState &gstate;
	shared_ptr<HashFilter> hf;
	//! Borrowed reference; lifetime tied to the PhysicalSJBuild operator,
	//! which outlives every task scheduled from this Finalize.
	const vector<idx_t> &build_col_ids;
	idx_t chunk_from;
	idx_t chunk_to;
};

class SJBuildHashInsertEvent : public BasePipelineEvent {
public:
	SJBuildHashInsertEvent(Pipeline &pipeline_p, ClientContext &context_p, const PhysicalSJBuild &op_p,
	                       SJBuildGlobalSinkState &gstate_p, idx_t filter_idx_p, HashFilter::HashKind hash_kind_p,
	                       const char *reason_p)
	    : BasePipelineEvent(pipeline_p), context(context_p), op(op_p), gstate(gstate_p), filter_idx(filter_idx_p),
	      hash_kind(hash_kind_p), reason(reason_p) {
	}

	void Schedule() override {
		const auto &build_col_ids = op.build_col_ids_per_filter[filter_idx];
		const auto &key_type = op.types[build_col_ids[0]];

		// Pre-size for total_data.Count() — upper bound on inserts after
		// NULL-filtering. Doubled in ReserveInline to keep load factor
		// ≤ 0.5 under worst-case all-unique + duplicate-race inputs.
		hf = make_shared_ptr<HashFilter>(hash_kind);
		hf->ReserveInline(key_type, gstate.total_data->Count());

		const idx_t cc = gstate.total_data->ChunkCount();
		const idx_t num_tasks = MaxValue<idx_t>((cc + SJ_BUILD_CHUNKS_PER_TASK - 1) / SJ_BUILD_CHUNKS_PER_TASK, 1);
		vector<shared_ptr<Task>> tasks;
		tasks.reserve(num_tasks);
		for (idx_t t = 0; t < num_tasks; t++) {
			const idx_t cf = t * SJ_BUILD_CHUNKS_PER_TASK;
			const idx_t ct = MinValue<idx_t>(cf + SJ_BUILD_CHUNKS_PER_TASK, cc);
			tasks.push_back(make_uniq<SJBuildHashInsertTask>(shared_from_this(), context, op, gstate, hf, build_col_ids,
			                                                 cf, ct));
		}
		SetTasks(std::move(tasks));
	}

	void FinishEvent() override {
		hf->Finalize();
		op.sj_to_create[filter_idx]->FinalizeAsHash(std::move(hf), reason);
	}

private:
	ClientContext &context;
	const PhysicalSJBuild &op;
	SJBuildGlobalSinkState &gstate;
	idx_t filter_idx;
	HashFilter::HashKind hash_kind;
	//! Static string for the DUCKDB_SJ_KERNEL_TRACE diagnostic — why this filter
	//! took the hash kernel ("force_hash" / "budget0" / "ineligible" / "overflow").
	const char *reason;
	shared_ptr<HashFilter> hf;
};

class SJBuildBitmapInitEvent : public BasePipelineEvent {
public:
	SJBuildBitmapInitEvent(Pipeline &pipeline_p, ClientContext &context_p, const PhysicalSJBuild &op_p,
	                       SJBuildGlobalSinkState &gstate_p, idx_t filter_idx_p, idx_t bitmap_budget_p,
	                       HashFilter::HashKind hash_kind_p, idx_t col_id_p, LogicalTypeId type_id_p)
	    : BasePipelineEvent(pipeline_p), context(context_p), op(op_p), gstate(gstate_p), filter_idx(filter_idx_p),
	      bitmap_budget(bitmap_budget_p), hash_kind(hash_kind_p), col_id(col_id_p), type_id(type_id_p) {
	}

	void Schedule() override {
		const idx_t cc = gstate.total_data->ChunkCount();
		const idx_t num_tasks = MaxValue<idx_t>((cc + SJ_BUILD_CHUNKS_PER_TASK - 1) / SJ_BUILD_CHUNKS_PER_TASK, 1);
		scratch = make_shared_ptr<SJBuildFilterScratch>();
		scratch->partials.resize(num_tasks);
		vector<shared_ptr<Task>> tasks;
		tasks.reserve(num_tasks);
		for (idx_t t = 0; t < num_tasks; t++) {
			const idx_t cf = t * SJ_BUILD_CHUNKS_PER_TASK;
			const idx_t ct = MinValue<idx_t>(cf + SJ_BUILD_CHUNKS_PER_TASK, cc);
			tasks.push_back(make_uniq<SJBuildBitmapScanTask>(shared_from_this(), context, op, gstate, scratch, t, cf, ct,
			                                                 col_id, type_id));
		}
		SetTasks(std::move(tasks));
	}

	void FinishEvent() override {
		const auto reduced = KeyBitmap::ReduceMinMax(scratch->partials);
		const auto &build_col_ids = op.build_col_ids_per_filter[filter_idx];
		const auto &key_type = op.types[build_col_ids[0]];
		auto bm = KeyBitmap::Allocate(context, reduced, key_type, bitmap_budget);
		if (!bm) {
			// Range exceeded budget — fall back to HashFilter. Every
			// KeyBitmap-eligible type (INTEGER, BIGINT, UINTEGER, DATE) is
			// also HashFilter::IsInline64Eligible, so the parallel INLINE_64
			// path is always available here. Chained from this FinishEvent
			// so it runs on the scheduler's thread pool, not blocking other
			// filters' events on the FinishEvent thread.
			vector<LogicalType> build_col_types {key_type};
			D_ASSERT(HashFilter::IsInline64Eligible(build_col_types));
			auto hash_event =
			    make_shared_ptr<SJBuildHashInsertEvent>(*pipeline, context, op, gstate, filter_idx, hash_kind,
			                                            "overflow");
			this->InsertEvent(std::move(hash_event));
			return;
		}
		if (bm->BitCount() == 0) {
			// Empty / all-NULL build — Allocate returned the zero-capacity
			// stub bitmap; no bits to set, finalize directly.
			op.sj_to_create[filter_idx]->FinalizeAsBitmap(std::move(bm));
			return;
		}
		scratch->bitmap = std::move(bm);
		auto fill_event = make_shared_ptr<SJBuildBitmapFillEvent>(*pipeline, context, op, gstate, filter_idx, col_id,
		                                                          type_id, scratch);
		this->InsertEvent(std::move(fill_event));
	}

private:
	ClientContext &context;
	const PhysicalSJBuild &op;
	SJBuildGlobalSinkState &gstate;
	idx_t filter_idx;
	idx_t bitmap_budget;
	HashFilter::HashKind hash_kind;
	idx_t col_id;
	LogicalTypeId type_id;
	shared_ptr<SJBuildFilterScratch> scratch;
};

// Reference: DPT physical_create_bf.cpp `PhysicalCreateBF::Finalize` (line ~403).
// Differences from DPT:
//   - No is_successful / give-up logic (plan-3 non-goal).
//   - No FinalizeMinMax / dynamic table filter (plan-3 non-goal).
//   - Bitmap-first + hash fallback per filter (plan-3 §"Build flow").
//   - Within-filter parallel KeyBitmap build via SJBuildBitmap{Init,Fill}Event,
//     matching the parallelism axis of mainline `PhysicalHashJoin` so the
//     benchmark comparison is apples-to-apples. Parallel HashFilter build is
//     deferred to Stage 2 — force_hash and bitmap-overflow paths stay
//     sequential through BuildOneFilterAsHash.
SinkFinalizeType PhysicalSJBuild::Finalize(Pipeline &pipeline, Event &event, ClientContext &context,
                                           OperatorSinkFinalizeInput &input) const {
	auto &gstate = input.global_state.Cast<SJBuildGlobalSinkState>();

	// Fold per-thread collections into the global one.
	for (auto &local : gstate.local_data_collections) {
		gstate.total_data->Combine(*local);
	}
	gstate.local_data_collections.clear();

	const auto budget = GetBitmapBudget(context);
	const auto hash_kind = GetHashKind(context);

	for (idx_t f = 0; f < sj_to_create.size(); f++) {
		const auto &filter = sj_to_create[f];
		const auto &build_col_ids = build_col_ids_per_filter[f];

		vector<LogicalType> build_col_types;
		build_col_types.reserve(build_col_ids.size());
		for (auto cid : build_col_ids) {
			if (cid >= types.size()) {
				throw InternalException("PhysicalSJBuild::Finalize: build_col_id out of range");
			}
			build_col_types.emplace_back(types[cid]);
		}

		const auto elig = KeyBitmap::CheckEligibility(build_col_ids, build_col_types);
		const bool must_hash = filter->force_hash() || !elig.eligible || budget == 0;
		const bool hash_is_parallelizable = HashFilter::IsInline64Eligible(build_col_types);
		// Static reason string for the DUCKDB_SJ_KERNEL_TRACE diagnostic; only
		// meaningful when must_hash. force_hash wins, then the budget=0 escape
		// hatch, else the type/arity was not bitmap-eligible.
		const char *hash_reason =
		    filter->force_hash() ? "force_hash" : (budget == 0 ? "budget0" : "ineligible");

		if (must_hash && hash_is_parallelizable) {
			// Parallel INLINE_64 hash — atomic-CAS slot claim via SJBuildHashInsertEvent.
			auto hash_event =
			    make_shared_ptr<SJBuildHashInsertEvent>(pipeline, context, *this, gstate, f, hash_kind, hash_reason);
			event.InsertEvent(std::move(hash_event));
		} else if (must_hash) {
			// Sequential BOXED hash (varchar / decimal / composite).
			// Parallel BOXED build is Stage 3, not yet implemented.
			BuildOneFilterAsHash(context, *gstate.total_data, filter, build_col_ids, hash_kind, hash_reason);
		} else {
			// Parallel bitmap init→fill event chain; scheduler load-balances
			// across filters and within-filter tasks.
			auto init_event = make_shared_ptr<SJBuildBitmapInitEvent>(pipeline, context, *this, gstate, f, budget,
			                                                          hash_kind, elig.col_id, elig.type_id);
			event.InsertEvent(std::move(init_event));
		}
	}
	return SinkFinalizeType::READY;
}

// ===========================================================================
// Source — re-emit materialised data so downstream operators read through
//           this operator without a second scan of the build subtree.
//
// Reference: DPT physical_create_bf.cpp `CreateBFGlobalSourceState` /
// `CreateBFLocalSourceState` / `GetData` (lines ~443–497). Same idiom: scan
// `gstate.total_data` (the post-Combine ColumnDataCollection). We don't
// implement DPT's external/partitioned scan paths since plan-3 doesn't
// register with TemporaryMemoryManager.
// ===========================================================================

class SJBuildGlobalSourceState : public GlobalSourceState {
public:
	explicit SJBuildGlobalSourceState(const ColumnDataCollection &collection) : data_collection(collection) {
		collection.InitializeScan(scan_state);
	}

	idx_t MaxThreads() override {
		return MaxValue<idx_t>(data_collection.ChunkCount(), 1);
	}

	const ColumnDataCollection &data_collection;
	ColumnDataParallelScanState scan_state;
};

class SJBuildLocalSourceState : public LocalSourceState {
public:
	ColumnDataLocalScanState local_scan_state;
};

unique_ptr<GlobalSourceState> PhysicalSJBuild::GetGlobalSourceState(ClientContext &context) const {
	(void)context;
	if (!sink_state) {
		throw InternalException("PhysicalSJBuild::GetGlobalSourceState: sink_state not set");
	}
	auto &gstate = sink_state->Cast<SJBuildGlobalSinkState>();
	return make_uniq<SJBuildGlobalSourceState>(*gstate.total_data);
}

unique_ptr<LocalSourceState> PhysicalSJBuild::GetLocalSourceState(ExecutionContext &context,
                                                                  GlobalSourceState &gstate) const {
	(void)context;
	(void)gstate;
	return make_uniq<SJBuildLocalSourceState>();
}

SourceResultType PhysicalSJBuild::GetDataInternal(ExecutionContext &context, DataChunk &chunk,
                                                  OperatorSourceInput &input) const {
	(void)context;
	auto &gstate = input.global_state.Cast<SJBuildGlobalSourceState>();
	auto &lstate = input.local_state.Cast<SJBuildLocalSourceState>();
	gstate.data_collection.Scan(gstate.scan_state, lstate.local_scan_state, chunk);
	return chunk.size() == 0 ? SourceResultType::FINISHED : SourceResultType::HAVE_MORE_OUTPUT;
}

// ===========================================================================
// Pipeline wiring — mirrors RPT / DPT's PhysicalCreateBF.
//
// References:
//   - DPT physical_create_bf.cpp `BuildPipelines` (line ~530) — sink-of-its-
//     own-child-meta-pipeline + source-of-current pattern.
//   - DPT physical_create_bf.cpp `BuildPipelinesFromRelated` (line ~499) —
//     idempotent dependency wiring across multiple probes sharing one build.
//
// Behaviour:
//   - First BuildPipelines call: creates `this_pipeline` (the build pipeline)
//     as a child meta-pipeline of the current. Builds children[0] into it.
//   - First BuildPipelinesFromRelated call (when no Source-side BuildPipelines
//     ran first): same — creates the build pipeline.
//   - Subsequent BuildPipelinesFromRelated calls: idempotent — just adds a
//     dependency from `current` to the existing `this_pipeline`. Probes thus
//     wait on the build's Finalize.
// ===========================================================================

void PhysicalSJBuild::BuildPipelines(Pipeline &current, MetaPipeline &meta_pipeline) {
	op_state.reset();
	sink_state.reset();
	D_ASSERT(children.size() == 1);

	auto &state = meta_pipeline.GetState();
	state.SetPipelineSource(current, *this);
	if (!this_pipeline) {
		auto &child_meta_pipeline = meta_pipeline.CreateChildMetaPipeline(current, *this);
		this_pipeline = child_meta_pipeline.GetBasePipeline();
		child_meta_pipeline.Build(children[0].get());
	} else {
		current.AddDependency(this_pipeline);
	}
}

void PhysicalSJBuild::BuildPipelinesFromRelated(Pipeline &current, MetaPipeline &meta_pipeline) {
	op_state.reset();
	D_ASSERT(children.size() == 1);

	if (!this_pipeline) {
		auto &child_meta_pipeline = meta_pipeline.CreateChildMetaPipeline(current, *this);
		this_pipeline = child_meta_pipeline.GetBasePipeline();
		child_meta_pipeline.Build(children[0].get());
	} else {
		current.AddDependency(this_pipeline);
	}
}

} // namespace duckdb
