// Dynamically linked, read-only EXPLAIN client for diagnostic observers.
#include "duckdb.hpp"

#include <fstream>
#include <iostream>
#include <sstream>
#include <stdexcept>

int main(int argc, char **argv) {
	if (argc != 3) {
		std::cerr << "usage: explain_original DATABASE QUERY_SQL\n";
		return 2;
	}
	try {
		std::ifstream input(argv[2]);
		if (!input) {
			throw std::runtime_error("cannot read original query");
		}
		std::stringstream sql;
		sql << input.rdbuf();
		duckdb::DBConfig config;
		config.options.access_mode = duckdb::AccessMode::READ_ONLY;
		config.options.maximum_threads = 1;
		duckdb::DuckDB database(argv[1], &config);
		duckdb::Connection connection(database);
		auto statements = connection.ExtractStatements(sql.str());
		if (statements.size() != 1 || statements[0]->type != duckdb::StatementType::SELECT_STATEMENT) {
			throw std::runtime_error("expected exactly one original SELECT");
		}
		auto setup = connection.Query("SET threads=1; SET memory_limit='4GB'; SET disabled_optimizers='';");
		if (setup->HasError()) {
			throw std::runtime_error(setup->GetError());
		}
		auto result = connection.Query("EXPLAIN (FORMAT JSON) " + sql.str());
		if (result->HasError()) {
			throw std::runtime_error(result->GetError());
		}
		if (result->RowCount() != 1 || result->ColumnCount() != 2) {
			throw std::runtime_error("unexpected EXPLAIN result shape");
		}
		std::cout << result->GetValue(1, 0).ToString() << '\n';
	} catch (const std::exception &error) {
		std::cerr << error.what() << '\n';
		return 1;
	}
	return 0;
}
