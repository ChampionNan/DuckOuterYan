WITH RECURSIVE MovieSeries AS (
    SELECT 
        t.id AS title_id,
        t.title,
        t.production_year,
        t.season_nr,
        t.episode_nr,
        COALESCE(t.season_nr, 0) AS season_order
    FROM 
        title t
    WHERE 
        t.kind_id = (SELECT id FROM kind_type WHERE kind = 'series')
    UNION ALL
    SELECT 
        t.id,
        t.title,
        t.production_year,
        t.season_nr,
        t.episode_nr,
        COALESCE(t.season_nr, 0) + 1
    FROM 
        title t
    INNER JOIN MovieSeries ms ON t.episode_of_id = ms.title_id
),
ActorTitles AS (
    SELECT 
        ak.name AS actor_name,
        t.title AS movie_title,
        t.production_year,
        ROW_NUMBER() OVER (PARTITION BY ak.person_id ORDER BY t.production_year DESC) AS title_rank
    FROM 
        aka_name ak
    JOIN 
        cast_info ci ON ak.person_id = ci.person_id
    JOIN 
        aka_title t ON ci.movie_id = t.movie_id
    WHERE 
        ak.name IS NOT NULL
),
FilteredActors AS (
    SELECT 
        actor_name,
        movie_title,
        production_year
    FROM 
        ActorTitles
    WHERE 
        title_rank <= 3
),
CompanyMovies AS (
    SELECT 
        mc.movie_id,
        c.name AS company_name,
        ct.kind AS company_type,
        COUNT(*) AS movies_count
    FROM 
        movie_companies mc
    JOIN 
        company_name c ON mc.company_id = c.id
    JOIN 
        company_type ct ON mc.company_type_id = ct.id
    GROUP BY 
        mc.movie_id, c.name, ct.kind
),
MovieDetails AS (
    SELECT 
        ms.title_id,
        ms.title,
        ms.production_year,
        fam.actor_name,
        fam.movie_title,
        fam.production_year AS actor_year,
        COALESCE(companies.company_name, 'Independent') AS production_company,
        COALESCE(companies.movies_count, 0) AS number_of_movies
    FROM 
        MovieSeries ms
    LEFT JOIN 
        FilteredActors fam ON ms.title = fam.movie_title AND ms.production_year = fam.production_year
    LEFT JOIN 
        CompanyMovies companies ON ms.title_id = companies.movie_id
)
SELECT 
    md.title,
    md.production_year,
    md.actor_name,
    md.production_company,
    md.number_of_movies,
    CASE 
        WHEN md.number_of_movies > 0 THEN 'Produced by ' || md.production_company
        ELSE 'Independent Production'
    END AS production_message,
    SUM(CASE WHEN md.actor_year >= 2000 THEN 1 ELSE 0 END) OVER (PARTITION BY md.actor_name) AS Post2000Movies
FROM 
    MovieDetails md
WHERE 
    md.production_year >= 2000;
