#include "duckdb/optimizer/outer_yan/semi_join/semi_join_filter.hpp"

#include "duckdb/common/exception.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/hash_filter.hpp"
#include "duckdb/optimizer/outer_yan/semi_join/key_bitmap.hpp"

#include <cstdio>
#include <cstdlib>

namespace duckdb {

// Opt-in kernel-choice diagnostic. When the environment variable
// DUCKDB_SJ_KERNEL_TRACE is set (to any value), each finalized semi-join filter
// emits one line to stderr recording the kernel it committed to:
//   [SJ_KERNEL] BITMAP
//   [SJ_KERNEL] HASH reason=<force_hash|budget0|ineligible|overflow>
// This is the authoritative kind (it fires at the single commit chokepoint, so
// it reflects the runtime bitmap->hash overflow fallback too). The check is
// cached once: the env var cannot change within a process.
static bool SJKernelTraceEnabled() {
	static const bool enabled = std::getenv("DUCKDB_SJ_KERNEL_TRACE") != nullptr;
	return enabled;
}

SemiJoinFilter::SemiJoinFilter() : kind_(Kind::UNDECIDED) {
}

SemiJoinFilter::~SemiJoinFilter() = default;

void SemiJoinFilter::FinalizeAsBitmap(unique_ptr<KeyBitmap> b) {
	if (kind_ != Kind::UNDECIDED) {
		throw InternalException("SemiJoinFilter::FinalizeAsBitmap: already finalized");
	}
	bitmap_ = std::move(b);
	kind_ = Kind::BITMAP;
	if (SJKernelTraceEnabled()) {
		fprintf(stderr, "[SJ_KERNEL] BITMAP\n");
	}
}

void SemiJoinFilter::FinalizeAsHash(shared_ptr<HashFilter> h, const char *reason) {
	if (kind_ != Kind::UNDECIDED) {
		throw InternalException("SemiJoinFilter::FinalizeAsHash: already finalized");
	}
	hash_ = std::move(h);
	kind_ = Kind::HASH;
	if (SJKernelTraceEnabled()) {
		fprintf(stderr, "[SJ_KERNEL] HASH reason=%s\n", reason ? reason : "unknown");
	}
}

const KeyBitmap &SemiJoinFilter::bitmap() const {
	D_ASSERT(kind_ == Kind::BITMAP);
	return *bitmap_;
}

HashFilter &SemiJoinFilter::hash() const {
	D_ASSERT(kind_ == Kind::HASH);
	return *hash_;
}

shared_ptr<HashFilter> SemiJoinFilter::hash_shared() const {
	D_ASSERT(kind_ == Kind::HASH);
	return hash_;
}

bool SemiJoinFilter::IsEmpty() const {
	switch (kind_) {
	case Kind::UNDECIDED:
		// Callers must not probe before Finalize; treat as "no matches" defensively.
		return true;
	case Kind::BITMAP:
		return bitmap_->IsEmpty();
	case Kind::HASH:
		return hash_->IsEmpty();
	}
	throw InternalException("SemiJoinFilter::IsEmpty: unreachable");
}

} // namespace duckdb
