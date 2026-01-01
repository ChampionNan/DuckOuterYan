create or replace temp view s1 as select * from S where exists (select 1 from R where S.src = R.dst);
create or replace temp view t1 as select * from T where exists (select 1 from s1 where T.src = s1.dst);
create or replace temp view aggk as select K.src, min(K.dst) as annot from K group by K.src;
create or replace temp view aggt as select t1.src, min(annot) as annot from t1 full outer join aggk on t1.dst = aggk.src group by t1.src;
create or replace temp view aggs as select s1.src, min(annot) as annot from s1 full outer join aggt on s1.dst = aggt.src group by s1.src;
select aggs.src, min(annot) as total from R full outer join aggs on R.dst = aggs.src group by aggs.src;