SELECT * FROM (d1 FULL OUTER JOIN fact ON d1.k=fact.fk1) RIGHT OUTER JOIN d3 ON fact.fk3=d3.k;
