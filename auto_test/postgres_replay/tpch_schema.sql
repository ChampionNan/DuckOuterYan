-- TPC-H schema matching DuckDB's bundled dbgen column types at SF0.01.
-- Primary keys mirror auto_test/build_db.sh; foreign keys and a lineitem PK are
-- intentionally absent so plan selection is comparable to the DuckDB dataset.

CREATE SCHEMA IF NOT EXISTS public;

CREATE TABLE public.region (
    r_regionkey INTEGER NOT NULL PRIMARY KEY,
    r_name VARCHAR NOT NULL,
    r_comment VARCHAR NOT NULL
);

CREATE TABLE public.nation (
    n_nationkey INTEGER NOT NULL PRIMARY KEY,
    n_name VARCHAR NOT NULL,
    n_regionkey INTEGER NOT NULL,
    n_comment VARCHAR NOT NULL
);

CREATE TABLE public.supplier (
    s_suppkey BIGINT NOT NULL PRIMARY KEY,
    s_name VARCHAR NOT NULL,
    s_address VARCHAR NOT NULL,
    s_nationkey INTEGER NOT NULL,
    s_phone VARCHAR NOT NULL,
    s_acctbal NUMERIC(15, 2) NOT NULL,
    s_comment VARCHAR NOT NULL
);

CREATE TABLE public.customer (
    c_custkey BIGINT NOT NULL PRIMARY KEY,
    c_name VARCHAR NOT NULL,
    c_address VARCHAR NOT NULL,
    c_nationkey INTEGER NOT NULL,
    c_phone VARCHAR NOT NULL,
    c_acctbal NUMERIC(15, 2) NOT NULL,
    c_mktsegment VARCHAR NOT NULL,
    c_comment VARCHAR NOT NULL
);

CREATE TABLE public.part (
    p_partkey BIGINT NOT NULL PRIMARY KEY,
    p_name VARCHAR NOT NULL,
    p_mfgr VARCHAR NOT NULL,
    p_brand VARCHAR NOT NULL,
    p_type VARCHAR NOT NULL,
    p_size INTEGER NOT NULL,
    p_container VARCHAR NOT NULL,
    p_retailprice NUMERIC(15, 2) NOT NULL,
    p_comment VARCHAR NOT NULL
);

CREATE TABLE public.partsupp (
    ps_partkey BIGINT NOT NULL,
    ps_suppkey BIGINT NOT NULL,
    ps_availqty BIGINT NOT NULL,
    ps_supplycost NUMERIC(15, 2) NOT NULL,
    ps_comment VARCHAR NOT NULL,
    PRIMARY KEY (ps_partkey, ps_suppkey)
);

CREATE TABLE public.orders (
    o_orderkey BIGINT NOT NULL PRIMARY KEY,
    o_custkey BIGINT NOT NULL,
    o_orderstatus VARCHAR NOT NULL,
    o_totalprice NUMERIC(15, 2) NOT NULL,
    o_orderdate DATE NOT NULL,
    o_orderpriority VARCHAR NOT NULL,
    o_clerk VARCHAR NOT NULL,
    o_shippriority INTEGER NOT NULL,
    o_comment VARCHAR NOT NULL
);

CREATE TABLE public.lineitem (
    l_orderkey BIGINT NOT NULL,
    l_partkey BIGINT NOT NULL,
    l_suppkey BIGINT NOT NULL,
    l_linenumber BIGINT NOT NULL,
    l_quantity NUMERIC(15, 2) NOT NULL,
    l_extendedprice NUMERIC(15, 2) NOT NULL,
    l_discount NUMERIC(15, 2) NOT NULL,
    l_tax NUMERIC(15, 2) NOT NULL,
    l_returnflag VARCHAR NOT NULL,
    l_linestatus VARCHAR NOT NULL,
    l_shipdate DATE NOT NULL,
    l_commitdate DATE NOT NULL,
    l_receiptdate DATE NOT NULL,
    l_shipinstruct VARCHAR NOT NULL,
    l_shipmode VARCHAR NOT NULL,
    l_comment VARCHAR NOT NULL
);
