SELECT * FROM (d1 INNER JOIN fact ON d1.k=fact.fk1) INNER JOIN d2 ON fact.fk2=d2.k;
