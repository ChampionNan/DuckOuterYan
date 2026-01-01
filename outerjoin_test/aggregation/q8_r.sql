create or replace temp view s1 as select * from S where exists (select 1 from T where S.dst = T.src);
create or replace temp view s2 as select * from s1 where exists (select 1 from R where s1.src = R.dst);
create or replace temp view r1 as select * from R where exists (select 1 from s2 where R.dst = s2.src);
create or replace temp view t1 as select * from T where exists (select 1 from s2 where T.src = s2.dst);
create or replace temp view aggk as select K.src, max(K.dst) as annot from K group by K.src;
create or replace temp view aggt as select t1.src, max(annot) as annot from t1 full outer join aggk on t1.dst = aggk.src group by t1.src;
create or replace temp view aggs as select s2.src, max(annot) as annot from s2 right outer join aggt on s2.dst = aggt.src group by s2.src;
select aggs.src, max(annot) as total from r1 right outer join aggs on r1.dst = aggs.src group by aggs.src;