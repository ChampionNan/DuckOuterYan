create or replace temp view r1 as select * from R where exists (select 1 from S where R.dst = S.src);
create or replace temp view t1 as select * from T where exists (select 1 from S where S.dst = T.src);
select r1.src as v1, r1.dst as v2, S.src as v3, S.dst as v4, t1.src as v5, t1.dst as v6 from r1 right outer join (S left outer join t1 on S.dst = t1.src) on r1.dst = S.src;