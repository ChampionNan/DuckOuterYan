create or replace temp view s1 as select * from S where exists (select 1 from R where R.dst = S.src);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
select r1.src as v1, r1.dst as v2, s1.src as v3, s1.dst as v4, T.src as v5, T.dst as v6 from r1 right outer join (s1 full outer join T on s1.dst = T.src) on r1.dst = s1.src;