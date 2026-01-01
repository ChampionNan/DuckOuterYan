create or replace temp view t1 as select * from T where exists (select 1 from K where T.dst = K.src);
create or replace temp view s1 as select * from S where exists (select 1 from t1 where S.dst = t1.src);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
create or replace temp view s2 as select * from s1 where exists (select 1 from r1 where s1.src = r1.dst);
create or replace temp view t2 as select * from t1 where exists (select 1 from s2 where t1.src = s2.dst);
create or replace temp view aggk as select K.src, sum(K.dst) as annot from K group by K.src;
create or replace temp view aggt as select t2.src, sum(annot) as annot from t2 right outer join aggk on t2.dst = aggk.src group by t2.src;
create or replace temp view aggs as select s2.src, sum(annot) as annot from s2 right outer join aggt on s2.dst = aggt.src group by s2.src;
select r1.src, sum(annot) as total from r1 right outer join aggs on r1.dst = aggs.src group by r1.src;