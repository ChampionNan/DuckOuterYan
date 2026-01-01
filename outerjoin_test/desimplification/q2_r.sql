create or replace temp view s1 as select * from S where exists (select 1 from T where S.dst = T.src);
create or replace temp view r1 as select * from R where exists (select 1 from s1 where R.dst = s1.src);
create or replace temp view s2 as select * from s1 where exists (select 1 from r1 where s1.src = r1.dst);
create or replace temp view t1 as select * from T where exists (select 1 from s2 where T.src = s2.dst);
select R.src as v1, R.dst as v2, S.src as v3, S.dst as v4, T.src as v5, T.dst as v6, K.src as v7, K.dst as v8 from r1 as R right outer join (s2 as S right outer join (t1 as T full outer join K on T.dst = K.src) on S.dst = T.src) on R.dst = S.src;