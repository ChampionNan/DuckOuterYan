SELECT c_mktsegment, AVG(l_quantity) AS avg_qty FROM ((customer LEFT OUTER JOIN orders ON c_custkey=o_custkey) INNER JOIN lineitem ON o_orderkey=l_orderkey) GROUP BY c_mktsegment;
