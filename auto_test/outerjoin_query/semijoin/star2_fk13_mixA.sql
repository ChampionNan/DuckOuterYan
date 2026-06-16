SELECT * FROM (fact LEFT OUTER JOIN d1 ON fact.fk1=d1.k) INNER JOIN d3 ON fact.fk3=d3.k;
