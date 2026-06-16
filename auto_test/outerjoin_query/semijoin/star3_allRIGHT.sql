SELECT * FROM ((fact RIGHT OUTER JOIN d1 ON fact.fk1=d1.k) RIGHT OUTER JOIN d2 ON fact.fk2=d2.k) RIGHT OUTER JOIN d3 ON fact.fk3=d3.k;
