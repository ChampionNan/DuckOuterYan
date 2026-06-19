WITH RecentMovies AS (
    SELECT 
        t.id AS movie_id,
        t.title,
        t.production_year,
        k.keyword,
        ARRAY_AGG(CONCAT_WS(' - ', a.name, rt.role)) AS cast_list
    FROM 
        aka_title t
    JOIN 
        movie_keyword mk ON t.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    JOIN 
        cast_info ci ON t.id = ci.movie_id
    JOIN 
        aka_name a ON ci.person_id = a.person_id
    JOIN 
        role_type rt ON ci.role_id = rt.id
    WHERE 
        t.production_year > 2010
    GROUP BY 
        t.id, t.title, t.production_year, k.keyword
),

MovieInfo AS (
    SELECT 
        m.id AS movie_id,
        m.info,
        it.info AS info_type
    FROM 
        movie_info m
    JOIN 
        info_type it ON m.info_type_id = it.id
    WHERE 
        it.info LIKE '%trivia%' OR it.info LIKE '%facts%'
),

CompanyDetails AS (
    SELECT 
        mc.movie_id,
        cn.name AS company_name,
        ct.kind AS company_type
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
)

SELECT 
    rm.movie_id,
    rm.title,
    rm.production_year,
    rm.keyword,
    rm.cast_list,
    mi.info AS trivia_info,
    cd.company_name,
    cd.company_type
FROM 
    RecentMovies rm
LEFT JOIN 
    MovieInfo mi ON rm.movie_id = mi.movie_id
LEFT JOIN 
    CompanyDetails cd ON rm.movie_id = cd.movie_id;
