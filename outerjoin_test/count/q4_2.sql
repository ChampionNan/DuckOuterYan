create or replace temp view r1 as select * from R where exists (select 1 from S where R.dst = S.src);
create or replace temp view s1 as select * from S where exists (select 1 from r1 where S.src = r1.dst);
SELECT r1.src, COUNT(*) as cnt FROM r1 RIGHT OUTER JOIN (s1 FULL OUTER JOIN T ON s1.dst = T.src) ON r1.dst = s1.src GROUP BY r1.src;