WITH RankedTitles AS (
    SELECT 
        a.id AS aka_id,
        a.person_id,
        a.name AS aka_name,
        m.id AS movie_id,
        m.title,
        m.production_year,
        ROW_NUMBER() OVER (PARTITION BY a.person_id ORDER BY m.production_year DESC) AS title_rank
    FROM 
        aka_name AS a
    JOIN 
        cast_info AS c ON a.person_id = c.person_id
    JOIN 
        aka_title AS m ON c.movie_id = m.movie_id
),
TopRankedTitles AS (
    SELECT 
        aka_id,
        person_id,
        aka_name,
        movie_id,
        title,
        production_year
    FROM 
        RankedTitles
    WHERE 
        title_rank = 1
),
CompanyInfo AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies AS mc
    JOIN 
        company_name AS c ON mc.company_id = c.id
    JOIN 
        company_type AS ct ON mc.company_type_id = ct.id
),
MovieDetails AS (
    SELECT 
        t.title,
        t.production_year,
        COALESCE(ci.company_name, 'Unknown') AS company_name,
        COALESCE(ci.company_type, 'N/A') AS company_type,
        COUNT(cf.id) AS cast_count
    FROM 
        TopRankedTitles AS tr
    LEFT JOIN 
        CompanyInfo AS ci ON tr.movie_id = ci.movie_id
    LEFT JOIN 
        cast_info AS cf ON tr.movie_id = cf.movie_id
    JOIN 
        title AS t ON tr.movie_id = t.id
    GROUP BY 
        t.title, t.production_year, ci.company_name, ci.company_type
)
SELECT 
    m.title,
    m.production_year,
    m.company_name,
    m.company_type,
    m.cast_count
FROM 
    MovieDetails AS m;
