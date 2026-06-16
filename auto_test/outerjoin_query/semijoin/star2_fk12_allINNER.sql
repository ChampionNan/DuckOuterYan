SELECT * FROM (fact INNER JOIN d1 ON fact.fk1=d1.k) INNER JOIN d2 ON fact.fk2=d2.k;
