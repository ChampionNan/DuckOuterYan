SELECT * FROM (d1 INNER JOIN fact ON d1.k=fact.fk1) INNER JOIN d3 ON fact.fk3=d3.k;
