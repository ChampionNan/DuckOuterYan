WITH MovieDetails AS (
    SELECT 
        T.title AS movie_title,
        T.production_year,
        COALESCE(K.keyword, 'No Keywords') AS movie_keyword,
        C.kind AS company_type,
        P.info AS person_info,
        COUNT(CI.id) AS cast_count
    FROM 
        title T
    LEFT JOIN 
        movie_companies MC ON T.id = MC.movie_id
    LEFT JOIN 
        company_type C ON MC.company_type_id = C.id
    LEFT JOIN 
        movie_keyword MK ON T.id = MK.movie_id
    LEFT JOIN 
        keyword K ON MK.keyword_id = K.id
    LEFT JOIN 
        complete_cast CC ON T.id = CC.movie_id
    LEFT JOIN 
        cast_info CI ON CC.subject_id = CI.person_id AND CI.movie_id = T.id
    LEFT JOIN 
        person_info P ON CI.person_id = P.person_id
    GROUP BY 
        T.title, T.production_year, K.keyword, C.kind, P.info
),
TopMovies AS (
    SELECT 
        movie_title,
        production_year,
        movie_keyword,
        company_type,
        person_info,
        cast_count,
        ROW_NUMBER() OVER (PARTITION BY production_year ORDER BY cast_count DESC) AS rank
    FROM 
        MovieDetails
)

SELECT 
    movie_title,
    production_year,
    movie_keyword,
    company_type,
    person_info,
    cast_count
FROM 
    TopMovies
WHERE 
    rank <= 5;
