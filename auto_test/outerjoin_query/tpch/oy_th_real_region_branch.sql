SELECT r_name, n_name, c_name, s_name
FROM region
    LEFT OUTER JOIN nation   ON r_regionkey = n_regionkey
    LEFT OUTER JOIN customer ON n_nationkey = c_nationkey
    LEFT OUTER JOIN supplier ON n_nationkey = s_nationkey
WHERE r_regionkey < 4;
