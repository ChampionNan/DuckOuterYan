SELECT * FROM (fact LEFT OUTER JOIN d1 ON fact.fk1=d1.k) LEFT OUTER JOIN d2 ON fact.fk2=d2.k;
