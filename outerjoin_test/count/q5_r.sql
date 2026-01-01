create or replace temp view s1 as select * from S where exists (select 1 from R where R.dst = S.src);
create or replace temp view aggt as select T.src, count(*) as cnt from T group by T.src;
create or replace temp view joins as select s1.src, aggt.cnt from s1 full outer join aggt on s1.dst = aggt.src;
select R.src, sum(COALESCE(cnt, 1)) as cnt from R full outer join joins on R.dst = joins.src group by R.src;