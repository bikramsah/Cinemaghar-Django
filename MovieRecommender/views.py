from django.shortcuts import render, HttpResponseRedirect
from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.models import User, Group
from .forms import SignUpForm, AddMovieForm, LoginForm, AddRatingForm
from .models import Movie, Rating
from django.contrib import messages
import pandas as pd
from math import sqrt
import numpy as np
from math import ceil

# Create your views here.

def filterMovieByGenre():
    # Filtering by genres
    allMovies = []
    genresMovie = Movie.objects.values('genres', 'id')
    genres = {item["genres"] for item in genresMovie}
    
    for genre in genres:
        movie = Movie.objects.filter(genres=genre)
        n = len(movie)
        nSlides = n // 4 + ceil((n / 4) - (n // 4))
        allMovies.append([movie, range(1, nSlides), nSlides])
    
    params = {'allMovies': allMovies}
    return params


def generateRecommendation(request):
    movies = Movie.objects.all()
    ratings = Rating.objects.all()
    movie_data = []
    rating_data = []

    # Create movie DataFrame
    for movie in movies:
        movie_data.append([movie.id, movie.title, movie.movieduration, movie.image.url, movie.genres])
    
    movies_df = pd.DataFrame(movie_data, columns=['movieId', 'title', 'movieduration', 'image', 'genres'])
    
    # Create rating DataFrame
    for rating in ratings:
        rating_data.append([rating.user.id, rating.movie.id, rating.rating])
    
    rating_df = pd.DataFrame(rating_data, columns=['userId', 'movieId', 'rating'])
    
    # Convert the columns to appropriate types
    rating_df['userId'] = rating_df['userId'].astype(int)
    rating_df['movieId'] = rating_df['movieId'].astype(int)
    rating_df['rating'] = rating_df['rating'].astype(float)

    if request.user.is_authenticated:
        userid = request.user.id
        
        # Get user's watched movies
        user_ratings = Rating.objects.select_related('movie').filter(user=userid)
        if user_ratings.count() == 0:
            return None  # No ratings available for the user
        
        # Create input DataFrame for user
        input_data = []
        for rating in user_ratings:
            input_data.append([rating.movie.title, rating.rating])
        
        input_movies = pd.DataFrame(input_data, columns=['title', 'rating'])
        input_movies['rating'] = input_movies['rating'].astype(float)

        # Filter out movies based on titles the user has rated
        input_ids = movies_df[movies_df['title'].isin(input_movies['title'].tolist())]
        input_movies = pd.merge(input_ids, input_movies, on='title')

        # Find other users who have watched the same movies
        user_subset = rating_df[rating_df['movieId'].isin(input_movies['movieId'].tolist())]
        user_subset_group = user_subset.groupby('userId')

        # Sort user groups by number of movies in common
        user_subset_group = sorted(user_subset_group, key=lambda x: len(x[1]), reverse=True)

        # Calculate Pearson correlation for similarity
        pearson_correlation_dict = {}
        for name, group in user_subset_group:
            group = group.sort_values(by='movieId')
            input_movies = input_movies.sort_values(by='movieId')
            n_ratings = len(group)
            
            temp_df = input_movies[input_movies['movieId'].isin(group['movieId'].tolist())]
            temp_ratings = temp_df['rating'].tolist()
            group_ratings = group['rating'].tolist()
            
            Sxx = sum([i**2 for i in temp_ratings]) - pow(sum(temp_ratings), 2) / float(n_ratings)
            Syy = sum([i**2 for i in group_ratings]) - pow(sum(group_ratings), 2) / float(n_ratings)
            Sxy = sum(i * j for i, j in zip(temp_ratings, group_ratings)) - sum(temp_ratings) * sum(group_ratings) / float(n_ratings)
            
            if Sxx != 0 and Syy != 0:
                pearson_correlation_dict[name] = Sxy / sqrt(Sxx * Syy)
            else:
                pearson_correlation_dict[name] = 0

        pearson_df = pd.DataFrame.from_dict(pearson_correlation_dict, orient='index', columns=['similarityIndex'])
        pearson_df['userId'] = pearson_df.index

        # Merge with ratings
        top_users = pearson_df.merge(rating_df, left_on='userId', right_on='userId')
        top_users['weightedRating'] = top_users['similarityIndex'] * top_users['rating']
        recommendation_df = top_users.groupby('movieId').sum()[['similarityIndex', 'weightedRating']]
        recommendation_df['weighted average recommendation score'] = recommendation_df['weightedRating'] / recommendation_df['similarityIndex']
        
        # Sort by recommendation score
        recommendation_df = recommendation_df.sort_values(by='weighted average recommendation score', ascending=False)
        top_movie_ids = recommendation_df.head(5).index
        
        # Return recommended movies
        recommended_movies = movies_df[movies_df['movieId'].isin(top_movie_ids)]
        return recommended_movies.to_dict('records')

    return None


# Other views remain the same

            

            




def signup(request):
    if not request.user.is_authenticated:
        if request.method=='POST':
            fm=SignUpForm(request.POST)
            if fm.is_valid():
                user=fm.save()
                group=Group.objects.get(name='Editor')
                user.groups.add(group)
                messages.success(request,'Account Created Successfully!!!')
        else:
            if not request.user.is_authenticated:
                fm=SignUpForm()
        return render(request,'MovieRecommender/signup.html',{'form':fm})
    else:
        return HttpResponseRedirect('/home/')

def user_login(request):
    if not request.user.is_authenticated:
        if request.method=='POST':
            fm=LoginForm(request=request,data=request.POST)
            if fm.is_valid():
                uname=fm.cleaned_data['username']
                upass=fm.cleaned_data['password']
                user=authenticate(username=uname,password=upass)
                if user is not None:
                    login(request,user)
                    messages.success(request,'Logged in Successfully!!')
                    return HttpResponseRedirect('/dashboard/')
        else:
            fm=LoginForm()
        return render(request,'MovieRecommender/login.html',{'form':fm})
    else:
        return HttpResponseRedirect('/dashboard/')



def home(request):
    params=filterMovieByGenre()
    params['recommended']=generateRecommendation(request)
    return render(request,'MovieRecommender/home.html',params)

def addmovie(request):
    if request.user.is_authenticated:
        if request.method=='POST':
            fm=AddMovieForm(request.POST,request.FILES)
            if fm.is_valid():
                fm.save()
                messages.success(request,'Movie Added Successfully!!!')
        else:
            fm=AddMovieForm()
        return render(request,'MovieRecommender/addmovie.html',{'form':fm})
    else:
        return HttpResponseRedirect('/login/')


def dashboard(request):
    if request.user.is_authenticated: 
        params=filterMovieByGenre()
        params['user']=request.user
        if request.method=='POST':
            userid=request.POST.get('userid')
            movieid=request.POST.get('movieid')
            movie=Movie.objects.all()
            u=User.objects.get(pk=userid)
            m=Movie.objects.get(pk=movieid)
            rfm=AddRatingForm(request.POST)
            params['rform']=rfm
            if rfm.is_valid():
                rat=rfm.cleaned_data['rating']
                count=Rating.objects.filter(user=u,movie=m).count()
                if(count>0):
                    messages.warning(request,'You have already submitted your review!!')
                    return render(request,'MovieRecommender/dashboard.html',params)
                action=Rating(user=u,movie=m,rating=rat)
                action.save()
                messages.success(request,'You have submitted'+' '+rat+' '+"star")
            return render(request,'MovieRecommender/dashboard.html',params)
        else:
            #print(request.user.id)
            rfm=AddRatingForm()
            params['rform']=rfm
            movie=Movie.objects.all()
            return render(request,'MovieRecommender/dashboard.html',params)
    else:
        return HttpResponseRedirect('/login/')
            
def user_logout(request):
    if request.user.is_authenticated:
        logout(request)
        return HttpResponseRedirect('/login/')


def profile(request):
    if request.user.is_authenticated:
        #"select sum(rating) from Rating where user=request.user.id"
        r=Rating.objects.filter(user=request.user.id)
        totalReview=0
        for item in r:
            totalReview+=int(item.rating)
        #select count(*) from Rating where user=request.user.id"
        totalwatchedmovie=Rating.objects.filter(user=request.user.id).count()
        return render(request,'MovieRecommender/profile.html',{'totalReview':totalReview,'totalwatchedmovie':totalwatchedmovie})
    else:
        return HttpResponseRedirect('/login/')




