create or replace temp view s1 as select * from S where exists (select 1 from T where S.dst = T.src);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
create or replace temp view s2 as select * from s1 where exists (select 1 from r1 where s1.src = r1.dst);
create or replace temp view t1 as select * from T where exists (select 1 from s2 where T.src = s2.dst);
SELECT r1.src, COUNT(*) as cnt FROM r1 RIGHT OUTER JOIN (s2 RIGHT OUTER JOIN (t1 FULL OUTER JOIN K ON t1.dst = K.src) ON s2.dst = t1.src) ON r1.dst = s2.src GROUP BY r1.src;