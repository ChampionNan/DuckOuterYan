create or replace temp view r1 as SELECT * FROM R where exists (SELECT 1 FROM S WHERE R.dst = S.src);
create or replace temp view s1 as SELECT * FROM S where exists (SELECT 1 FROM r1 WHERE r1.dst = S.src);
create or replace temp view t1 as SELECT * FROM T where exists (SELECT 1 FROM s1 WHERE s1.dst = T.src);
SELECT r1.src as v1, r1.dst as v2, s1.src as v3, s1.dst as v4, t1.src as v5, t1.dst as v6 FROM r1 INNER JOIN (s1 LEFT OUTER JOIN t1 ON s1.dst = t1.src) ON r1.dst = s1.src;