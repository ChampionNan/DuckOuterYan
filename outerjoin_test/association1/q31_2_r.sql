create or replace temp view s1 as select * from S where exists (select 1 from T where S.dst = T.src);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
create or replace temp view t1 as select * from T where exists (select 1 from s1 where T.src = s1.dst);
SELECT r1.src as v1, r1.dst as v2, s1.src as v3, s1.dst as v4, t1.src as v5, t1.dst as v6 FROM r1 RIGHT OUTER JOIN (s1 INNER JOIN t1 ON s1.dst = t1.src) ON r1.dst = s1.src;