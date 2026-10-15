// Execute one unchanged SELECT and fully drain it, without SQL wrappers.
#include "duckdb.hpp"

#include <chrono>
#include <fstream>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>

using namespace duckdb;

static void JSONString(std::ostream &out, const string &value) {
	out << '"';
	for (unsigned char byte : value) {
		if (byte == '"' || byte == '\\') {
			out << '\\' << char(byte);
		} else if (byte < 32) {
			out << "\\u00" << "0123456789abcdef"[byte >> 4] << "0123456789abcdef"[byte & 15];
		} else {
			out << char(byte);
		}
	}
	out << '"';
}

int main(int argc, char **argv) {
	if (argc != 6) {
		std::cerr << "usage: bare_query_runner DATABASE QUERY_SQL {OFF|ON} PROFILE_OR_- ROWS_OR_-\n";
		return 2;
	}
	try {
		const string mode = argv[3], profile = argv[4], output = argv[5];
		if (mode != "OFF" && mode != "ON") {
			throw std::runtime_error("mode must be OFF or ON");
		}
		std::ifstream input(argv[2]);
		if (!input) {
			throw std::runtime_error("cannot read query file");
		}
		std::stringstream sql;
		sql << input.rdbuf();
		DBConfig config;
		config.options.access_mode = AccessMode::READ_ONLY;
		config.options.maximum_threads = 1;
		DuckDB database(argv[1], &config);
		Connection connection(database);
		auto statements = connection.ExtractStatements(sql.str());
		if (statements.size() != 1 || statements[0]->type != StatementType::SELECT_STATEMENT) {
			throw std::runtime_error("expected exactly one bare SELECT");
		}
		auto configure = [&](const string &text) {
			auto result = connection.Query(text);
			if (result->HasError()) {
				throw std::runtime_error(result->GetError());
			}
		};
		configure("SET threads=1; SET memory_limit='4GB'; SET max_execution_time=600000; "
		          "SET disabled_optimizers='" + string(mode == "OFF" ? "outer_yan" : "") + "';");
		if (profile != "-") {
			configure("CALL enable_profiling(format='json', save_location=" + Value(profile).ToSQLString() + ");");
		}
		std::ofstream rows;
		if (output != "-") {
			rows.open(output, std::ios::binary);
			if (!rows) {
				throw std::runtime_error("cannot open correctness output");
			}
		}
		const auto start = std::chrono::steady_clock::now();
		auto result = connection.SendQuery(sql.str());
		if (result->HasError()) {
			throw std::runtime_error(result->GetError());
		}
		idx_t count = 0;
		while (auto chunk = result->Fetch()) {
			count += chunk->size();
			if (!rows.is_open()) {
				continue;
			}
			for (idx_t row = 0; row < chunk->size(); row++) {
				rows << '[';
				for (idx_t column = 0; column < chunk->ColumnCount(); column++) {
					if (column) {
						rows << ',';
					}
					// Quoted SQL values distinguish NULL from text and retain decimal
					// precision; JSON escaping keeps every result row on one line.
					JSONString(rows, chunk->GetValue(column, row).ToSQLString());
				}
				rows << "]\n";
			}
		}
		if (result->HasError()) {
			throw std::runtime_error(result->GetError());
		}
		const double elapsed = std::chrono::duration<double, std::milli>(std::chrono::steady_clock::now() - start).count();
		if (rows.is_open()) {
			rows.close();
			if (!rows) {
				throw std::runtime_error("failed to write complete correctness result");
			}
		}
		std::cout << std::setprecision(12) << "[BARE_RUN] {\"mode\":\"" << mode << "\",\"elapsed_ms\":" << elapsed
		          << ",\"rows\":" << count << ",\"profiled\":" << (profile == "-" ? "false" : "true")
		          << ",\"exported\":" << (output == "-" ? "false" : "true") << ",\"types\":[";
		for (idx_t index = 0; index < result->types.size(); index++) {
			if (index) {
				std::cout << ',';
			}
			JSONString(std::cout, result->types[index].ToString());
		}
		std::cout << "]}\n";
	} catch (const std::exception &error) {
		std::cerr << error.what() << '\n';
		return 1;
	}
	return 0;
}
