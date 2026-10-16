/* Stream one bare integer/NULL SELECT with libpq, without a cursor or COPY. */
#include <libpq-fe.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static int integer_field(const char *value, int length) {
    int i = length > 0 && value[0] == '-' ? 1 : 0;
    if (i == length) return 0;
    for (; i < length; i++) if (value[i] < '0' || value[i] > '9') return 0;
    return 1;
}

static int json_string(const char *value, int length) {
    if (fputc('"', stdout) == EOF) return 0;
    for (int i = 0; i < length; i++) {
        unsigned char byte = (unsigned char) value[i];
        if (byte == '"' || byte == '\\') {
            if (fputc('\\', stdout) == EOF || fputc(byte, stdout) == EOF) return 0;
        } else if (byte < 32) {
            if (fprintf(stdout, "\\u00%02x", byte) < 0) return 0;
        } else if (fputc(byte, stdout) == EOF) return 0;
    }
    return fputc('"', stdout) != EOF;
}

int main(int argc, char **argv) {
    const size_t max_sql = 1024 * 1024;
    PGconn *connection = NULL;
    PGresult *result = NULL;
    char *sql = NULL, *end = NULL;
    uint64_t rows = 0;
    int completed = 0, status = 1;
    long columns;
    if (argc < 6 || argc > 7 || (argc == 7 && strcmp(argv[6], "jsonl"))) {
        fprintf(stderr, "usage: pg_bare_query HOST PORT USER DATABASE COLUMNS [jsonl] < query.sql\n");
        return 1;
    }
    columns = strtol(argv[5], &end, 10);
    if (*end || columns < 1 || columns > 64) {
        fprintf(stderr, "invalid result column count\n");
        return 1;
    }
    sql = malloc(max_sql + 2);
    if (!sql) goto cleanup;
    size_t length = fread(sql, 1, max_sql + 1, stdin);
    if (ferror(stdin) || length > max_sql || memchr(sql, 0, length)) {
        fprintf(stderr, "invalid or oversized SQL input\n");
        goto cleanup;
    }
    sql[length] = 0;
    const char *keys[] = {"host", "port", "user", "dbname", "connect_timeout", NULL};
    const char *values[] = {argv[1], argv[2], argv[3], argv[4], "10", NULL};
    connection = PQconnectdbParams(keys, values, 0);
    if (PQstatus(connection) != CONNECTION_OK || !PQsendQuery(connection, sql) ||
        !PQsetSingleRowMode(connection)) {
        fprintf(stderr, "%s", PQerrorMessage(connection));
        goto cleanup;
    }
    /* The server receives the original SET statements and SELECT unchanged.
     * Single-row mode controls only client buffering; release each row promptly. */
    setvbuf(stdout, NULL, _IOFBF, 1024 * 1024);
    while ((result = PQgetResult(connection)) != NULL) {
        ExecStatusType kind = PQresultStatus(result);
        if (kind == PGRES_SINGLE_TUPLE) {
            if (completed || PQnfields(result) != columns || PQntuples(result) != 1) {
                fprintf(stderr, "unexpected SELECT result shape\n");
                goto cleanup;
            }
            if (argc == 7 && fputc('[', stdout) == EOF) goto output_error;
            for (int i = 0; i < columns; i++) {
                const char *value = PQgetisnull(result, 0, i) ? "NULL" : PQgetvalue(result, 0, i);
                int size = PQgetisnull(result, 0, i) ? 4 : PQgetlength(result, 0, i);
                if (argc == 7) {
                    Oid type = PQftype(result, i);
                    if (type != 20 && type != 21 && type != 23 && type != 25 && type != 1043) {
                        fprintf(stderr, "JSONL comparison supports integer and text columns only\n");
                        goto cleanup;
                    }
                    if (i && fputc(',', stdout) == EOF) goto output_error;
                    if (PQgetisnull(result, 0, i)) {
                        if (fputs("null", stdout) == EOF) goto output_error;
                    } else if (!json_string(value, size)) goto output_error;
                    continue;
                }
                if (!PQgetisnull(result, 0, i) && !integer_field(value, size)) {
                    fprintf(stderr, "SELECT contains a non-integer field\n");
                    goto cleanup;
                }
                if ((i && fputc(',', stdout) == EOF) || fwrite(value, 1, (size_t) size, stdout) != (size_t) size)
                    goto output_error;
            }
            if (argc == 7 && fputc(']', stdout) == EOF) goto output_error;
            if (fputc('\n', stdout) == EOF) goto output_error;
            rows++;
        } else if (kind == PGRES_TUPLES_OK) {
            char expected[32];
            snprintf(expected, sizeof(expected), "%llu", (unsigned long long) rows);
            if (++completed != 1 || PQnfields(result) != columns || PQntuples(result) != 0 ||
                strncmp(PQcmdStatus(result), "SELECT ", 7) || strcmp(PQcmdTuples(result), expected)) {
                fprintf(stderr, "missing or inconsistent SELECT completion\n");
                goto cleanup;
            }
        } else if (kind != PGRES_COMMAND_OK || strcmp(PQcmdStatus(result), "SET")) {
            fprintf(stderr, "unexpected query result: %s: %s\n", PQresStatus(kind), PQresultErrorMessage(result));
            goto cleanup;
        }
        PQclear(result);
        result = NULL;
    }
    if (completed != 1 || PQstatus(connection) != CONNECTION_OK) {
        fprintf(stderr, "incomplete SELECT: %s\n", PQerrorMessage(connection));
        goto cleanup;
    }
    if (fflush(stdout) == EOF) goto output_error;
    fprintf(stderr, "[PGSTREAM] rows=%llu columns=%ld completed=1\n", (unsigned long long) rows, columns);
    status = 0;
    goto cleanup;
output_error:
    perror("writing SELECT result");
cleanup:
    PQclear(result);
    PQfinish(connection);
    free(sql);
    return status;
}
