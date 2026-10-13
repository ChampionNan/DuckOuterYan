#include "catch.hpp"
#include "test_helpers.hpp"
#include "duckdb/main/profiling_node.hpp"

#include <iostream>
#include <thread>

using namespace duckdb;

static idx_t MaximumOperatorMemory(const ProfilingNode &node, MetricType metric) {
	idx_t maximum = 0;
	for (auto &child : node.children) {
		maximum = MaxValue(maximum, child->GetProfilingInfo().GetMetricValue<idx_t>(metric));
		maximum = MaxValue(maximum, MaximumOperatorMemory(*child, metric));
	}
	return maximum;
}

TEST_CASE("Query profiler retains operator buffer observations", "[api][memory_profile]") {
	DuckDB db(nullptr);
	Connection con(db);
	REQUIRE_NO_FAIL(con.Query("SET threads=4"));
	REQUIRE_NO_FAIL(con.Query("CREATE TABLE memory_profile_input AS SELECT range AS i FROM range(200000)"));
	con.EnableProfiling();
	con.context->config.emit_profiler_output = false;
	const string query = "SELECT i % 53 AS k, count(*) FROM memory_profile_input GROUP BY k ORDER BY k";
	for (idx_t run = 0; run < 2; run++) {
		REQUIRE_NO_FAIL(con.Query(query));
		auto tree = con.GetProfilingTree();
		REQUIRE(tree);
		const auto memory = MaximumOperatorMemory(*tree, MetricType::SYSTEM_PEAK_BUFFER_MEMORY);
		REQUIRE(memory > 0);
		REQUIRE(memory == tree->GetProfilingInfo().GetMetricValue<idx_t>(MetricType::SYSTEM_PEAK_BUFFER_MEMORY));
		const auto spill = MaximumOperatorMemory(*tree, MetricType::SYSTEM_PEAK_TEMP_DIR_SIZE);
		REQUIRE(spill == tree->GetProfilingInfo().GetMetricValue<idx_t>(MetricType::SYSTEM_PEAK_TEMP_DIR_SIZE));
	}
}

TEST_CASE("Test query profiler", "[api]") {
	duckdb::unique_ptr<QueryResult> result;
	DuckDB db(nullptr);
	Connection con(db);
	string output;

	con.EnableQueryVerification();
	con.EnableProfiling();
	// don't pollute the console with profiler info.
	con.context->config.emit_profiler_output = false;

	string query = "SELECT * FROM (SELECT 42) tbl1, (SELECT 33) tbl2";
	REQUIRE_NO_FAIL(con.Query(query));

	output = con.GetProfilingInformation();
	REQUIRE(output.size() > 0);
	bool query_found_in_output = output.find(query) != std::string::npos;
	REQUIRE(query_found_in_output);

	output = con.GetProfilingInformation(ProfilerPrintFormat::JSON);
	REQUIRE(output.size() > 0);
	query_found_in_output = output.find(query) != std::string::npos;
	REQUIRE(query_found_in_output);
}

TEST_CASE("Test query profiler, no query in the profiling output.", "[api]") {
	duckdb::unique_ptr<QueryResult> result;
	DuckDB db(nullptr);
	Connection con(db);
	string output;

	con.EnableQueryVerification();
	con.EnableProfiling();
	// don't pollute the console with profiler info.
	con.context->config.emit_profiler_output = false;

	// Disable `QUERY_NAME` in profiling output.
	REQUIRE_NO_FAIL(con.Query(R"(PRAGMA custom_profiling_settings = '{"QUERY_NAME": "false"}')"));
	string query = "SELECT * FROM (SELECT 42) tbl1, (SELECT 33) tbl2";
	REQUIRE_NO_FAIL(con.Query(query));

	output = con.GetProfilingInformation();
	REQUIRE(output.size() > 0);
	bool query_not_found_in_output = output.find(query) == std::string::npos;
	REQUIRE(query_not_found_in_output);

	output = con.GetProfilingInformation(ProfilerPrintFormat::JSON);
	REQUIRE(output.size() > 0);
	query_not_found_in_output = output.find(query) == std::string::npos;
	REQUIRE(query_not_found_in_output);
}

TEST_CASE("Test latency when interrupting query", "[api]") {
	duckdb::unique_ptr<QueryResult> result;
	DuckDB db(nullptr);
	Connection con(db);

	con.EnableQueryVerification();
	con.EnableProfiling();

	con.context->config.emit_profiler_output = false;

	// Test interupting a query and running a new one afterward.
	// The latency should reflect the new one.
	std::thread t([&con]() {
		string query = "explain analyze select sum(range) from range(1_000_000_000);";
		con.Query(query);
	});

	std::this_thread::sleep_for(std::chrono::milliseconds(100));
	con.Interrupt();
	t.join();

	string query = "explain analyze select 42;";
	REQUIRE_NO_FAIL(con.Query(query));

	auto profiling_info = con.GetProfilingTree()->GetProfilingInfo();
	auto latency = profiling_info.GetMetricValue<double>(MetricType::LATENCY);
	auto query_name = profiling_info.GetMetricValue<string>(MetricType::QUERY_NAME);
	REQUIRE(query == query_name);
	REQUIRE(latency > 0);
	REQUIRE(latency < 0.1);
}
