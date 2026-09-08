"""Pinned active-corpus exclusions; never read machine-local experiment results.

The reference run recorded 28 OFF correctness-gate timeouts at 48 threads.
Seven remain active to preserve graph bushy and TPC-H core star coverage.
Hashes pin the checked-in SQL selected for exclusion, not the server SQL:
the historical result did not record SQL hashes. Component sources stay intact.
"""

REFERENCE_RUN = "experiment_onoff_benchmark_20260830_002656"
REFERENCE_THREADS = 48
TIMEOUT_SECONDS = 1800
TIMEOUT_PHASE = "correctness_off"

# Active paths and current component SQL hashes. Changes require explicit review.
EXCLUDED_QUERY_HASHES = {
    "tpcds/derived__ojb_tpcds_q72_fulfillment_ldmx.sql": "a7d7e4e2396fd9fe198a59a43f7c11d5971af132dcf1700c69fbcad4bae8702b",
    "tpcds/derived__ojb_tpcds_q72_fulfillment_rdmx.sql": "70401b52b908c05c12e9629100b6e637e60815a2f1fa75347e6a62dc523d635b",
    "tpcds/derived__ojb_tpcds_q72_fulfillment_bmx.sql": "b2518cc7715db47a2808cb54ba730aaa94d30a67c0fab8d113dc1891198908e8",
    "tpcds/derived__ojb_tpcds_q72_fulfillment_bdmx.sql": "bb9c595944a126ca9b5e773da42cb4e00d0b41c2742d13b1fca8f3ec0dfbc53e",
    "tpcds/derived__ojb_tpcds_q72_fulfillment_rduR.sql": "0adedf6a0e93abcc5a4dfbf04369e1549cec0ada1f9e210784e328ecc39fe860",
    "tpcds/derived__ojb_tpcds_q80_store_channel_ldmx.sql": "1fdfe2995b3855ba0ea874be36ffab1b665efd4745727c891ed30d081281644b",
    "tpcds/derived__ojb_tpcds_q80_store_channel_rdmx.sql": "cae6257bcc4cdf8bfaf9bbd202de5b5b17707c2ee01c9ac335718b59ec6bebee",
    "tpcds/derived__ojb_tpcds_q80_store_channel_rdax.sql": "d70a28864a4ee91e9a96389e2461b4229deb1f871da170b1ba9631bed23161e0",
    "tpcds/derived__ojb_tpcds_q93_return_reason_rdmx.sql": "4af5d8a9ae4f3accf5a160677d9d6011ae63bbfa05fce122f1af7d74db08e59e",
    "tpcds/derived__ojb_tpcds_q51_channel_balance_ldmx.sql": "475288a8c61ea3027d7c07a951f472c635e66f723f6b60cf99227ac4559faa41",
    "tpcds/derived__ojb_tpcds_q51_channel_balance_rdmx.sql": "3c3b4dd1ba7b58038f94a3d187b79f67e7716fee26869312db8772b315699f31",
    "tpcds/derived__ojb_tpcds_q51_channel_balance_alt.sql": "382e3d4b98d8e80001cf8c1320a76007d2d8013f6351bdd6fc91cb5a35b535c8",
    "tpcds/derived__ojb_tpcds_q51_channel_balance_rdax.sql": "580e143cd6de1649f00d436fd7b38a22f50679b5e931c0d8c976f3f80f249c40",
    "tpcds/derived__ojb_tpcds_q51_channel_balance_rduR.sql": "f330fdc362cbe93e27fdc11c8fbdd957a8a70896cbb8b593fdd3ef5c2a5f9d31",
    "tpcds/derived__ojb_sqlstorm_tpcds_11376_ldmx.sql": "de9a67b2fd05da923ede01f33659fdef01f007cfc0a5c02f4ce2380d3ba46ca8",
    "tpcds/derived__ojb_sqlstorm_tpcds_11376_rdmx.sql": "43396921ade81793626bed52c7477d8b5a5c13428c246b64d04257cb5610f770",
    "tpcds/derived__ojb_sqlstorm_tpcds_11376_bmx.sql": "7905c1acdadffce345eadb4d3a25afa597a4a61261cee646cb5f0b83bfb83a20",
    "tpcds/derived__ojb_sqlstorm_tpcds_11376_bdmx.sql": "9208d1f6325180a4494c03653352b936d6a4baf3d40da12cd7a7bb2d8f55d3d3",
    "tpcds/derived__ojb_sqlstorm_tpcds_11376_rduL.sql": "285a21446ca4a840bca1fbd14ddcae9c76b78f8883aba9f02bc9ca83ca9cb935",
    "tpch/industry__oy_th_real_custdist.sql": "f73baccefb24070fd4a7228dc519b56e225a2558ae5daf77ddcf078847848d86",
    "tpcds/industry__oy_ds_real_store_agg.sql": "101c2683da01730b79cdd82bfbe7f735ffaf41051f1d14e8376ea28b740d9cfd",
}

# User-requested exceptions: do not remove the only cases in these two patterns.
RETAINED_TIMEOUT_QUERY_PATHS = frozenset({
    "graph/derived__bushy_N5_mixA_s01.sql",
    "graph/derived__bushy_N5_mixC_s01.sql",
    "tpch/derived__ojb_tpch_q09_supply_chain_alt.sql",
    "tpch/derived__ojb_tpch_q09_supply_chain_ldmx.sql",
    "tpch/derived__ojb_tpch_q09_supply_chain_rdax.sql",
    "tpch/derived__ojb_tpch_q09_supply_chain_rdmx.sql",
    "tpch/derived__ojb_tpch_q09_supply_chain_rduL.sql",
})
