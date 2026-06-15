SELECT * FROM part LEFT OUTER JOIN partsupp ON p_partkey=ps_partkey LEFT OUTER JOIN supplier ON ps_suppkey=s_suppkey LEFT OUTER JOIN nation ON s_nationkey=n_nationkey;
