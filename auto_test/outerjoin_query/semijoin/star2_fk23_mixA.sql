SELECT * FROM (fact LEFT OUTER JOIN d2 ON fact.fk2=d2.k) INNER JOIN d3 ON fact.fk3=d3.k;
