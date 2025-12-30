create or replace temp view s1 as select * from S where exists (select 1 from T where S.dst = T.src);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
create or replace temp view s2 as select * from s1 where exists (select 1 from r1 where r1.dst = s1.src);
SELECT r1.src as v1, r1.dst as v2, s2.src as v3, s2.dst as v4, T.src as v5, T.dst as v6 FROM r1 right outer join (s2 right outer join T on s2.dst = T.src) on r1.dst = s2.src;