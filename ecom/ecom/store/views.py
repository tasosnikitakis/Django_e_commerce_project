from django.shortcuts import render, redirect
from .models import Product, Category, Profile
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
from django.contrib.auth.models import User
from django.contrib.auth.forms import UserCreationForm
from django import forms
from .forms import SignUpForm, UpdateUserForm, ChangePasswordForm, UserInfoForm
from django.db.models import Q
import json
from openai import OpenAI

import re
from cart.cart import Cart



from payment.forms import ShippingForm
from payment.models import ShippingAddress




# Create your views here.
def category(request, cat):
    # replace hyphens with spaces
    cat = cat.replace("-", " ")
    # grab category from url
    try:
        category = Category.objects.get(name=cat)
        products = Product.objects.filter(category=category)
        return render(request, "category.html", {"category": category, "products": products})
    except:
        messages.success(request, ("Category does not exist"))
        return redirect('home')


def category_summary(request):
    categories = Category.objects.all()
    return render(request, 'category_summary.html', {"categories": categories})


def product(request, pk):
    product = Product.objects.get(id=pk)
    return render(request, "product.html", {"product": product})


def home(request):
    products = Product.objects.all()
    return render(request, "home.html", {"products": products})


def about(request):
    return render(request, "about.html", {})


def login_user(request):
    if request.method == "POST":
        username = request.POST['username']
        password = request.POST['password']
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            # Do some shopping cart stuff
            current_user = Profile.objects.get(user__id=request.user.id)
            # Get their saved cart from database
            saved_cart = current_user.old_cart
            # Convert database string to python dictionary
            if saved_cart:
                # Convert to dictionary using JSON
                converted_cart = json.loads(saved_cart)
                # Add the loaded cart dictionary to our session
                # Get the cart
                cart = Cart(request)
                # Loop thru the cart and add the items from the database
                for key, value in converted_cart.items():
                    cart.db_add(product=key, quantity=value)

            messages.success(request, ("You have been logged in"))
            return redirect('home')
        else:
            messages.success(request, ("There was an error"))
            return redirect('home')
    else:
        return render(request, "login.html", {})


def logout_user(request):
    logout(request)
    messages.success(request, ("You have been logged out"))
    return redirect('home')


def register_user(request):
    form = SignUpForm()
    if request.method == "POST":
        form = SignUpForm(request.POST)
        if form.is_valid():
            form.save()
            username = form.cleaned_data['username']
            password = form.cleaned_data['password1']
            # log in user
            user = authenticate(username=username, password=password)
            login(request, user)
            messages.success(request, ("Username Created - Please Fill Out Your User Info Below..."))
            return redirect('update_info')
        else:
            messages.success(request, ("Whoops! There was a problem Registering, please try again..."))
            return redirect('register')
    else:
        return render(request, 'register.html', {'form': form})


def update_password(request):
    if request.user.is_authenticated:
        current_user = request.user
        # Did they fill out the form
        if request.method == 'POST':
            form = ChangePasswordForm(current_user, request.POST)
            # Is the form valid
            if form.is_valid():
                form.save()
                messages.success(request, "Your Password Has Been Updated...")
                login(request, current_user)
                return redirect('update_user')
            else:
                for error in list(form.errors.values()):
                    messages.error(request, error)
                    return redirect('update_password')
        else:
            form = ChangePasswordForm(current_user)
            return render(request, "update_password.html", {'form': form})
    else:
        messages.success(request, "You Must Be Logged In To View That Page...")
        return redirect('home')

    return render(request, "update_password.html", {})


def update_user(request):
    if request.user.is_authenticated:
        current_user = User.objects.get(id=request.user.id)
        user_form = UpdateUserForm(request.POST or None, instance=current_user)

        if user_form.is_valid():
            user_form.save()

            login(request, current_user)
            messages.success(request, "User Has Been Updated!!")
            return redirect('home')
        return render(request, "update_user.html", {'user_form': user_form})
    else:
        messages.success(request, "You Must Be Logged In To Access That Page!!")
        return redirect('home')


def update_info(request):
    if request.user.is_authenticated:
        # Get Current User
        current_user = Profile.objects.get(user__id=request.user.id)
        # Get Current User's Shipping Info
        shipping_user = ShippingAddress.objects.get(user__id=request.user.id)

        # Get original User Form
        form = UserInfoForm(request.POST or None, instance=current_user)
        # Get User's Shipping Form
        shipping_form = ShippingForm(request.POST or None, instance=shipping_user)
        if form.is_valid() or shipping_form.is_valid():
            # Save original form
            form.save()
            # Save shipping form
            shipping_form.save()

            messages.success(request, "Your Info Has Been Updated!!")
            return redirect('home')
        return render(request, "update_info.html", {'form': form, 'shipping_form': shipping_form})
    else:
        messages.success(request, "You Must Be Logged In To Access That Page!!")
        return redirect('home')


def search(request):
    if request.method == "POST":
        searched = request.POST['searched']
        # Query The Products DB Model
        searched = Product.objects.filter(Q(name__icontains=searched) | Q(description__icontains=searched))
        # Test for null
        if not searched:
            messages.success(request, "That Product Does Not Exist...Please try Again.")
            return render(request, "search.html", {})
        else:
            return render(request, "search.html", {'searched': searched})
    else:
        return render(request, "search.html", {})


def search_view(request):
    if request.method == "POST":
        query = request.POST.get('searched', '')

        if query:
            try:
                # Step 1: Use the new OpenAI API for chat completions
                response = client.chat.completions.create(model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are a helpful assistant that extracts relevant keywords from user queries."
                    },
                    {
                        "role": "user",
                        "content": f"Analyze this search query for a pharmacy product: {query}. Extract relevant keywords and give a description of what the user might be searching for."
                    }
                ])

                # Step 2: Extract keywords from the new response format
                gpt_text = response.choices[0].message.content
                keywords = extract_keywords_from_gpt_response(gpt_text)

                # Step 3: Query the database with the extracted keywords
                searched_products = Product.objects.filter(
                    Q(name__icontains=keywords.get('name', '')) |  # Handle missing keys
                    Q(description__icontains=keywords.get('description', '')) |
                    Q(category__name__icontains=keywords.get('category', ''))
                    # Ensure you're accessing the correct field
                )

                # Step 4: Generate an explanation for why these products were selected
                explanation = generate_explanation(query, searched_products)

                if not searched_products.exists():
                    messages.success(request, "That Product Does Not Exist... Please try Again.")
                    return render(request, "search_view.html",
                                  {'searched': [], 'explanation': "No matching products found."})

                return render(request, "search_view.html", {
                    'searched': searched_products,
                    'explanation': explanation,
                    'query': query
                })
            except Exception as e:
                messages.error(request, f"Error during the OpenAI request: {str(e)}")
                return render(request, "search_view.html",
                              {'searched': [], 'explanation': "There was an issue with the AI search."})

        else:
            messages.success(request, "Please enter a search term.")
            return render(request, "search_view.html", {'searched': [], 'explanation': "No search term entered."})

    else:
        return render(request, "search_view.html", {'searched': [], 'explanation': ''})


def extract_keywords_from_gpt_response(gpt_text):
    # Custom function to parse GPT's response and extract keywords for querying the database
    # This is a simplistic example - you could also enhance this with NLP models
    keywords = {
        'name': '',
        'description': '',
        'category': ''
    }
    # Logic to extract 'name', 'description', 'category' from GPT's text
    # Look for any mention of product names (simplified version, can be enhanced)
    name_matches = re.findall(r'product\sname:?\s([a-zA-Z0-9\s]+)', gpt_text, re.IGNORECASE)
    if name_matches:
        keywords['name'] = name_matches[0].strip()

    # Look for category-related keywords (simplified; categories can be expanded)
    category_matches = re.findall(r'category:?\s([a-zA-Z\s]+)', gpt_text, re.IGNORECASE)
    if category_matches:
        keywords['category'] = category_matches[0].strip()

    # Look for description or symptom mentions
    description_matches = re.findall(r'description:?\s([a-zA-Z\s]+)|for\s([a-zA-Z\s]+)', gpt_text, re.IGNORECASE)
    if description_matches:
        # Assuming the second group captures relevant search terms (like symptom, purpose)
        description = ' '.join([match[0] if match[0] else match[1] for match in description_matches])
        keywords['description'] = description.strip()

    return keywords


def generate_explanation(query, products):
    """
    Generates a default explanation based on the search query and found products.

    query: The search term entered by the user.
    products: A queryset of products found based on the search query.

    Returns:
    A user-friendly string explanation.
    """
    if not products.exists():
        return f"Sorry, we couldn't find any products matching '{query}'. Here are some suggestions for related products."

    # Craft a custom message explaining why these products were returned
    explanation = f"We found {products.count()} product(s) that match your search for '{query}': "

    # Include specific product names in the explanation
    product_names = ', '.join([product.name for product in products[:3]])  # Limiting to 3 for readability
    explanation += f"{product_names} and others."

    # If there's a specific sale product, we can highlight it
    sale_products = products.filter(is_sale=True)
    if sale_products.exists():
        sale_product_names = ', '.join([product.name for product in sale_products[:3]])  # Limit to 3 sale items
        explanation += f" Additionally, there are some sale items like {sale_product_names} that might interest you."

    return explanation
