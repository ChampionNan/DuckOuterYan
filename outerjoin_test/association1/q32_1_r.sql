create or replace temp view t1 as select * from T where exists (select 1 from S where S.dst = T.src);
create or replace temp view r1 as select * from R where exists (select 1 from S where R.dst = S.src);
select * from r1 right outer join S on r1.dst = S.src left outer join t1 on S.dst = t1.src;