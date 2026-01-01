create or replace temp view s1 as select * from S where exists (select 1 from R where R.dst = S.src);
create or replace temp view t1 as select * from T where exists (select 1 from s1 where T.src = s1.dst);
SELECT R.src, COUNT(*) as cnt FROM R FULL OUTER JOIN (s1 FULL OUTER JOIN (t1 FULL OUTER JOIN K ON t1.dst = K.src) ON s1.dst = t1.src) ON R.dst = s1.src GROUP BY R.src;