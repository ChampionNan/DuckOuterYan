WITH MovieDetails AS (
    SELECT 
        t.title AS movie_title,
        t.production_year,
        c.name AS company_name,
        kt.kind AS kind_type,
        k.keyword AS movie_keyword,
        pk.info AS person_info
    FROM title t
    JOIN movie_companies mc ON t.id = mc.movie_id
    JOIN company_name c ON mc.company_id = c.id
    JOIN company_type kt ON mc.company_type_id = kt.id
    LEFT JOIN movie_keyword mk ON t.id = mk.movie_id
    LEFT JOIN keyword k ON mk.keyword_id = k.id
    LEFT JOIN complete_cast cc ON t.id = cc.movie_id
    LEFT JOIN cast_info ci ON cc.subject_id = ci.person_id
    LEFT JOIN person_info pk ON ci.person_id = pk.person_id AND pk.info_type_id IN (
        SELECT id FROM info_type WHERE info LIKE '%bio%'
    )
    WHERE t.production_year >= 2000
),
AkaNames AS (
    SELECT 
        ak.name AS aka_name,
        ak.person_id
    FROM aka_name ak
    WHERE ak.name ILIKE '%star%'
),
AkaTitles AS (
    SELECT 
        at.title AS aka_title,
        at.movie_id
    FROM aka_title at
    WHERE at.title ILIKE '%adventure%'
),
RankedMovies AS (
    SELECT 
        md.movie_title,
        md.production_year,
        md.company_name,
        md.kind_type,
        md.movie_keyword,
        ak.aka_name,
        at.aka_title,
        ROW_NUMBER() OVER (PARTITION BY md.production_year ORDER BY md.production_year DESC) AS rank
    FROM MovieDetails md
    JOIN AkaNames ak ON md.production_year = ak.person_id
    JOIN AkaTitles at ON md.production_year = at.movie_id
)
SELECT 
    rank,
    movie_title,
    production_year,
    company_name,
    kind_type,
    movie_keyword,
    aka_name,
    aka_title
FROM RankedMovies
WHERE rank <= 10;
