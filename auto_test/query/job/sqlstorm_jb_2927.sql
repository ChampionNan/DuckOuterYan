WITH MovieInfo AS (
    SELECT 
        mt.title, 
        mt.production_year, 
        k.keyword, 
        mk.movie_id
    FROM 
        aka_title mt
    JOIN 
        movie_keyword mk ON mt.id = mk.movie_id
    JOIN 
        keyword k ON mk.keyword_id = k.id
    WHERE 
        mt.production_year > 2000
),
ActorInfo AS (
    SELECT 
        ak.name, 
        ci.movie_id, 
        ri.role,
        ROW_NUMBER() OVER (PARTITION BY ci.movie_id ORDER BY ak.name) as actor_rank
    FROM 
        cast_info ci
    JOIN 
        aka_name ak ON ci.person_id = ak.person_id
    JOIN 
        role_type ri ON ci.role_id = ri.id
),
CompanyInfo AS (
    SELECT 
        mc.movie_id, 
        cn.name AS company_name, 
        ct.kind AS company_type,
        COUNT(DISTINCT mc.id) AS company_count
    FROM 
        movie_companies mc
    JOIN 
        company_name cn ON mc.company_id = cn.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY 
        mc.movie_id, cn.name, ct.kind
)
SELECT 
    mi.title, 
    mi.production_year, 
    ai.name AS actor_name, 
    ai.role AS actor_role,
    ci.company_name,
    ci.company_type,
    ci.company_count
FROM 
    MovieInfo mi
LEFT JOIN 
    ActorInfo ai ON mi.movie_id = ai.movie_id AND ai.actor_rank <= 3
LEFT JOIN 
    CompanyInfo ci ON mi.movie_id = ci.movie_id
WHERE 
    (ai.name IS NOT NULL OR ci.company_name IS NOT NULL);
