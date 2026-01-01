create or replace temp view r1 as select * from R where exists (select 1 from S where R.dst = S.src);
create or replace temp view s1 as select * from S where exists (select 1 from r1 where S.src = r1.dst);
create or replace view aggt as select T.src, count(*) as cnt from T group by T.src;
create or replace temp view joins as select s1.src, aggt.cnt from s1 full outer join aggt on s1.dst = aggt.src;
create or replace temp view aggs as select src, sum(COALESCE(cnt, 1)) as cnt from joins group by src;
SELECT r1.src, sum(COALESCE(aggs.cnt, 1)) FROM r1 RIGHT OUTER JOIN aggs ON r1.dst = aggs.src GROUP BY r1.src;