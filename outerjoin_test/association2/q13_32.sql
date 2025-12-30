create or replace temp view s1 as select * from S where exists (select 1 from R where R.dst = S.src);
create or replace temp view s2 as select * from s1 where exists (select 1 from T where s1.dst = T.src);
create or replace temp view r1 as select * from R where exists (select 1 from s2 where R.dst = s2.src);
SELECT r1.src as v1, r1.dst as v2, s2.src as v3, s2.dst as v4, T.src as v5, T.dst as v6 FROM r1 right outer join (s2 right outer join T on s2.dst = T.src) on r1.dst = s2.src;