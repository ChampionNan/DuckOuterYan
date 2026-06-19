
WITH RankedMovies AS (
    SELECT 
        a.title,
        a.production_year,
        COUNT(*) OVER (PARTITION BY a.production_year) AS movie_count,
        ROW_NUMBER() OVER (PARTITION BY a.production_year ORDER BY a.production_year DESC, a.title) AS rn
    FROM 
        aka_title AS a
    JOIN 
        movie_keyword AS mk ON a.id = mk.movie_id
    JOIN 
        keyword AS k ON mk.keyword_id = k.id
    WHERE 
        k.keyword LIKE '%Adventure%'
),
TopMovies AS (
    SELECT
        title,
        production_year,
        movie_count
    FROM
        RankedMovies
    WHERE
        rn <= 5
),
DistinctCast AS (
    SELECT 
        DISTINCT ci.person_id,
        ci.movie_id,
        ct.kind AS role_type
    FROM
        cast_info AS ci
    JOIN 
        comp_cast_type AS ct ON ci.person_role_id = ct.id
    WHERE 
        ct.kind IS NOT NULL
),
PersonInfo AS (
    SELECT 
        n.id AS person_id,
        n.name,
        pi.info AS biography
    FROM 
        name AS n
    LEFT JOIN 
        person_info AS pi ON n.imdb_id = pi.person_id
    WHERE 
        pi.info_type_id = (SELECT id FROM info_type WHERE info = 'Biography') 
        OR pi.info_type_id IS NULL
)
SELECT 
    t.title,
    t.production_year,
    c.person_id,
    p.name,
    p.biography,
    ct.kind AS cast_type
FROM 
    TopMovies AS t
LEFT OUTER JOIN 
    movie_companies AS mc ON t.title = (SELECT title FROM aka_title WHERE id = mc.movie_id LIMIT 1)
LEFT JOIN 
    DistinctCast AS c ON t.title = (SELECT a.title FROM aka_title a WHERE a.id = c.movie_id LIMIT 1)
LEFT JOIN 
    PersonInfo AS p ON c.person_id = p.person_id
LEFT JOIN 
    comp_cast_type AS ct ON c.role_type = ct.kind
WHERE 
    (mc.company_type_id IS NULL OR mc.company_type_id IN (SELECT id FROM company_type WHERE kind = 'Distributor'))
    AND (t.production_year BETWEEN 2000 AND 2023 OR t.production_year IS NULL);
