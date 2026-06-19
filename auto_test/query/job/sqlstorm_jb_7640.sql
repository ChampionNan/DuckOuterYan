WITH RankedMovies AS (
    SELECT t.id AS movie_id, t.title, t.production_year, 
           ROW_NUMBER() OVER (PARTITION BY t.production_year ORDER BY t.id) AS rank
    FROM title t
    WHERE t.production_year IS NOT NULL
),
CompanyWithRoles AS (
    SELECT mc.movie_id, c.name AS company_name, ct.kind AS company_type, 
           ci.person_role_id, ci.nr_order
    FROM movie_companies mc
    JOIN company_name c ON mc.company_id = c.id
    JOIN company_type ct ON mc.company_type_id = ct.id
    JOIN complete_cast cc ON mc.movie_id = cc.movie_id
    JOIN cast_info ci ON cc.subject_id = ci.id
),
KeywordCounts AS (
    SELECT mk.movie_id, COUNT(DISTINCT k.keyword) AS keyword_count
    FROM movie_keyword mk
    JOIN keyword k ON mk.keyword_id = k.id
    GROUP BY mk.movie_id
)
SELECT rm.movie_id, rm.title, rm.production_year, 
       cwr.company_name, cwr.company_type, 
       kc.keyword_count
FROM RankedMovies rm
LEFT JOIN CompanyWithRoles cwr ON rm.movie_id = cwr.movie_id
LEFT JOIN KeywordCounts kc ON rm.movie_id = kc.movie_id
WHERE rm.rank <= 10;
