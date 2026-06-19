
WITH RankedMovies AS (
    SELECT 
        T.id AS movie_id,
        T.title,
        T.production_year,
        C.name AS company_name,
        RT.role AS role_name,
        COUNT(CI.person_id) AS cast_count
    FROM 
        title T
    LEFT JOIN 
        movie_companies MC ON T.id = MC.movie_id
    LEFT JOIN 
        company_name C ON MC.company_id = C.id
    LEFT JOIN 
        complete_cast CC ON T.id = CC.movie_id
    LEFT JOIN 
        cast_info CI ON CC.subject_id = CI.person_id
    LEFT JOIN 
        role_type RT ON CI.role_id = RT.id
    WHERE 
        T.production_year >= 2000
    GROUP BY 
        T.id, T.title, T.production_year, C.name, RT.role
),
TopMovies AS (
    SELECT 
        movie_id,
        title,
        production_year,
        company_name,
        role_name,
        cast_count,
        ROW_NUMBER() OVER (PARTITION BY role_name ORDER BY cast_count DESC) AS rank
    FROM 
        RankedMovies
)
SELECT 
    movie_id,
    title,
    production_year,
    company_name,
    role_name,
    cast_count
FROM 
    TopMovies
WHERE 
    rank <= 5;
