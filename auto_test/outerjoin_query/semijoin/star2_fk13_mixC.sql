SELECT * FROM (fact RIGHT OUTER JOIN d1 ON fact.fk1=d1.k) FULL OUTER JOIN d3 ON fact.fk3=d3.k;
