SELECT * FROM (fact FULL OUTER JOIN d2 ON fact.fk2=d2.k) FULL OUTER JOIN d3 ON fact.fk3=d3.k;
