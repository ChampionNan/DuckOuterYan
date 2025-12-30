create or replace temp view s1 as select * from S where exists (select 1 from R where R.dst = S.src);
create or replace temp view t1 as select * from T where exists (select 1 from s1 where s1.dst = T.src);
SELECT R.src as v1, R.dst as v2, s1.src as v3, s1.dst as v4, t1.src as v5, t1.dst as v6 FROM R LEFT OUTER JOIN s1 ON R.dst = s1.src LEFT OUTER JOIN t1 ON s1.dst = t1.src;