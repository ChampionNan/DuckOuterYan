SELECT * FROM (fact FULL OUTER JOIN d1 ON fact.fk1=d1.k) FULL OUTER JOIN d2 ON fact.fk2=d2.k;
