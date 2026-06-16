SELECT * FROM (d1 FULL OUTER JOIN fact ON d1.k=fact.fk1) FULL OUTER JOIN d2 ON fact.fk2=d2.k;
