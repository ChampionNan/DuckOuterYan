create or replace temp view s1 as select * from S where exists (select 1 from R where S.src = R.dst);
create or replace temp view t1 as select * from T where exists (select 1 from s1 where T.src = s1.dst);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
SELECT r1.src as v1, r1.dst as v2, s1.src as v3, s1.dst as v4, t1.src as v5, t1.dst as v6 FROM r1 INNER JOIN s1 ON r1.dst = s1.src LEFT OUTER JOIN t1 ON s1.dst = t1.src;