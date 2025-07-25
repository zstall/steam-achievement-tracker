# 🏆 Steam Achievement Tracker

A **production-ready Flask web application** that transforms Steam gaming into a social achievement experience. Track your Steam library, create custom challenges, and engage with a community of gamers through our Trophy Feed system.

![Project Status](https://img.shields.io/badge/Status-Phase%202%20Development-brightgreen)
![Database](https://img.shields.io/badge/Database-PostgreSQL-blue)
![Framework](https://img.shields.io/badge/Framework-Flask-lightgrey)
![License](https://img.shields.io/badge/License-MIT-green)

---

## 🌟 **Features**

### 🎮 **Steam Integration**
- **Steam Library Sync** - Fetch all your games and achievements via Steam Web API
- **Achievement Tracking** - Monitor progress across your entire Steam library
- **Real-time Progress** - See completion percentages and unlock statistics
- **Professional Loading** - Beautiful progress indicators during Steam data fetch

### 🏆 **Custom Achievements System**
- **Create Challenges** - Design your own gaming achievements with multiple condition types:
  - Complete all selected games 100%
  - Own all games in a collection
  - Reach total playtime targets across games
  - Unlock specific achievements
- **Achievement Images** - Upload custom images for your achievements
- **Progress Tracking** - Automatic progress calculation and completion detection

### 🌟 **Community Features**
- **Achievement Sharing** - Share your custom achievements with the community
- **Community Marketplace** - Browse and import achievements created by other users
- **Trophy Feed** - Real-time activity stream showing community achievements, shares, and imports
- **Social Discovery** - Find new gaming challenges and see what others are accomplishing

### 🔒 **Production-Ready Security**
- **Encrypted Storage** - Steam API keys secured with Fernet encryption
- **User Authentication** - Secure registration, login, and session management
- **Environment Configuration** - Production-ready config management
- **Database Security** - Proper relationships, constraints, and indexes

### 📱 **Modern UI/UX**
- **Steam-Themed Design** - Beautiful dark theme matching Steam's aesthetic
- **Responsive Layout** - Works perfectly on desktop and mobile
- **Interactive Components** - Loading indicators, notifications, and real-time updates
- **Professional Navigation** - Intuitive menu system and user flows

---

## 🚀 **Quick Start**

### **Prerequisites**
- Python 3.8+
- PostgreSQL 12+
- Docker (optional, for easy database setup)

### **Installation**

1. **Clone the Repository**
   ```bash
   git clone <your-repo>
   cd steam-project
   ```

2. **Install Dependencies**
   ```bash
   pip install -r requirements.txt
   ```

3. **Setup Database**
   ```bash
   # Option 1: Using Docker
   docker-compose up -d
   
   # Option 2: Local PostgreSQL
   createdb steam_tracker
   ```

4. **Configure Environment**
   ```bash
   cp .env.example .env
   # Edit .env with your database URL and Steam API credentials
   ```

5. **Initialize Database**
   ```bash
   python3 init_db.py
   ```

6. **Run Migration (if you have existing JSON data)**
   ```bash
   python3 migrate_data.py
   ```

7. **Start the Application**
   ```bash
   python3 app.py
   ```

8. **Visit Your App**
   Open http://localhost:5000 in your browser

---

## 📊 **Project Structure**

```
steam-project/
├── 📱 **Application Core**
│   ├── app.py                 # Main Flask application
│   ├── models.py              # SQLAlchemy database models
│   ├── config.py              # Environment-based configuration
│   └── requirements.txt       # Python dependencies
│
├── 🗄️ **Database & Migration**
│   ├── init_db.py            # Database initialization
│   ├── migrate_data.py       # JSON to PostgreSQL migration
│   ├── update_db.py          # Schema update scripts
│   └── docker-compose.yml    # PostgreSQL + Redis containers
│
├── 🎨 **Frontend Templates**
│   ├── templates/
│   │   ├── base.html         # Main layout with navigation
│   │   ├── index.html        # Steam library dashboard
│   │   ├── trophy_feed.html  # Community activity feed
│   │   ├── custom_achievements.html
│   │   ├── community_achievements.html
│   │   ├── create_achievement.html
│   │   ├── game_detail.html
│   │   ├── login.html & register.html
│   │   └── profile.html
│   └── static/
│       └── achievement_images/  # User-uploaded images
│
├── 📋 **Documentation**
│   ├── README.md             # This file
│   ├── ROADMAP.md           # Development roadmap
│   ├── PHASE1_PLAN.md       # Phase 1 implementation details
│   ├── TROPHY_FEED_SPEC.md  # Trophy Feed feature specification
│   └── LOADING_INDICATOR_FEATURE.md
│
├── 🧪 **Testing**
│   ├── test_app.py          # Application functionality tests
│   ├── test_trophy_feed.py  # Trophy Feed system tests
│   └── test_loading_indicator.py
│
└── ⚙️ **Configuration**
    ├── .env.example         # Environment variables template
    ├── .env                 # Your local environment (not in git)
    └── .gitignore
```

---

## 🛠️ **Technology Stack**

### **Backend**
- **[Flask](https://flask.palletsprojects.com/)** - Lightweight Python web framework
- **[SQLAlchemy](https://www.sqlalchemy.org/)** - Python SQL toolkit and ORM
- **[PostgreSQL](https://www.postgresql.org/)** - Advanced open-source database
- **[Flask-Login](https://flask-login.readthedocs.io/)** - User session management
- **[Cryptography](https://cryptography.io/)** - Modern encryption for Python

### **Frontend**
- **[Bootstrap 5](https://getbootstrap.com/)** - Responsive CSS framework
- **[Font Awesome](https://fontawesome.com/)** - Professional icon library
- **Vanilla JavaScript** - Custom interactions and AJAX
- **Steam-inspired Design** - Dark theme with gaming aesthetics

### **APIs & Services**
- **[Steam Web API](https://steamcommunity.com/dev)** - Game and achievement data
- **[Pillow (PIL)](https://pillow.readthedocs.io/)** - Image processing for uploads

---

## 🎯 **Key Features Deep Dive**

### **Trophy Feed System** 🏆
The heart of community engagement:

- **Real-time Activity Stream** - See what others are achieving
- **Activity Types:**
  - 🎯 Custom achievement creation
  - 🌟 Community achievement sharing
  - 📥 Achievement imports
  - 🎉 Game completions (coming soon)
  - ⭐ Progress milestones (coming soon)
- **Smart Filtering** - Filter by activity type, user, or timeframe
- **Auto-refresh** - Updates every 30 seconds
- **Mobile Optimized** - Perfect experience on all devices

### **Custom Achievement Engine** 🎮
Powerful achievement creation system:

- **Multiple Condition Types:**
  - **100% Completion** - Complete all achievements in selected games
  - **Game Collection** - Own specific games in your library
  - **Playtime Goals** - Reach total playtime across game sets
  - **Future:** Specific achievement unlocks, date ranges, difficulty tiers

- **Progress Tracking** - Automatic calculation of achievement progress
- **Visual Design** - Upload custom images for your achievements
- **Community Sharing** - One-click sharing to community marketplace

### **Steam Integration** ⚡
Professional Steam data management:

- **Complete Library Sync** - All games, achievements, and playtime
- **Batch Processing** - Efficient API usage with rate limiting
- **Progress Tracking** - Beautiful loading indicators during sync
- **Error Handling** - Graceful handling of Steam API issues
- **Encrypted Storage** - Secure Steam API key management

---

## 📈 **Development Progress**

### ✅ **Phase 1: Complete** (Production-Ready Foundation)
- [x] **Database Migration** - JSON to PostgreSQL with full data preservation
- [x] **Security Implementation** - Encryption, environment vars, secure auth
- [x] **Enhanced Authentication** - Registration, login, profile management
- [x] **User Experience** - Professional loading indicators and notifications
- [x] **Trophy Feed System** - Community activity tracking and display

### 🚀 **Phase 2: In Progress** (Performance & Community)
- [x] **Trophy Feed System** - Real-time community activity stream
- [ ] **Cloud File Storage** - AWS S3 + CDN for achievement images
- [ ] **Performance Optimization** - Caching, pagination, background jobs
- [ ] **API Rate Limiting** - Protection against Steam API abuse
- [ ] **Background Processing** - Async Steam data synchronization

### ⏳ **Phase 3: Planned** (Production Deployment)
- [ ] **Deployment Infrastructure** - Docker, CI/CD, hosting setup
- [ ] **Monitoring & Analytics** - Error tracking, usage analytics
- [ ] **Enhanced UX** - Advanced mobile features, notifications

---

## 🔧 **Configuration**

### **Environment Variables**
```bash
# Flask Configuration
SECRET_KEY=your-secret-key-here
FLASK_ENV=development

# Database Configuration
DATABASE_URL=postgresql://user:pass@localhost:5432/steam_tracker

# Security Configuration
STEAM_ENCRYPTION_KEY=your-generated-fernet-key

# Optional: Redis for Caching
REDIS_URL=redis://localhost:6379/0

# File Upload Configuration
MAX_CONTENT_LENGTH=5242880
UPLOAD_FOLDER=static/achievement_images
```

### **Steam API Setup**
1. Get your Steam API key: https://steamcommunity.com/dev/apikey
2. Find your Steam ID: https://steamid.io/
3. Add both to your profile in the application

---

## 🧪 **Testing**

Run the comprehensive test suite:

```bash
# Test core application functionality
python3 test_app.py

# Test Trophy Feed system
python3 test_trophy_feed.py

# Test loading indicators
python3 test_loading_indicator.py
```

**Test Coverage:**
- ✅ Database models and relationships
- ✅ User authentication and security
- ✅ Achievement creation and sharing
- ✅ Trophy Feed activity logging
- ✅ Steam API integration
- ✅ UI components and navigation

---

## 🚀 **Usage Examples**

### **Creating Your First Custom Achievement**
1. **Sync Steam Data** - Click "Refresh Data" to load your Steam library
2. **Create Achievement** - Go to "My Achievements" → "Create New"
3. **Set Conditions** - Choose games and completion criteria
4. **Add Visual** - Upload a custom achievement image
5. **Share** - Make it available to the community!

### **Discovering Community Challenges**
1. **Browse Community** - Visit "Community" to see shared achievements
2. **Check Compatibility** - See which challenges you can complete
3. **Import Challenge** - Add interesting achievements to your collection
4. **Track Progress** - Monitor your progress toward completion

### **Following Community Activity**
1. **Trophy Feed** - Check the real-time activity stream
2. **Filter Activity** - Focus on specific types or users
3. **Discover Trends** - See what challenges are popular
4. **Get Inspired** - Find new gaming goals from the community

---

## 🤝 **Contributing**

We welcome contributions! Here's how to get started:

1. **Fork the Repository**
2. **Create Feature Branch** (`git checkout -b feature/AmazingFeature`)
3. **Commit Changes** (`git commit -m 'Add AmazingFeature'`)
4. **Push to Branch** (`git push origin feature/AmazingFeature`)
5. **Open Pull Request**

### **Development Guidelines**
- Follow the existing code style and structure
- Add tests for new features
- Update documentation for significant changes
- Test thoroughly before submitting PRs

---

## 📝 **License**

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙏 **Acknowledgments**

- **Steam Web API** for providing comprehensive gaming data
- **Flask Community** for the excellent web framework
- **Bootstrap Team** for the responsive design framework
- **All Contributors** who help make this project better

---

## 📞 **Support & Contact**

- **Issues:** [GitHub Issues](https://github.com/your-username/steam-project/issues)
- **Documentation:** Check the `/docs` folder for detailed guides
- **Community:** Join our discussions in the Trophy Feed!

---

## 🎮 **About**

**Steam Achievement Tracker** transforms solo gaming into a social experience. By combining Steam's rich achievement data with community-driven custom challenges, we create a platform where gamers can discover new goals, share creative challenges, and celebrate gaming accomplishments together.

Whether you're a casual gamer looking for new challenges or a completionist showcasing your achievements, our platform provides the tools and community to enhance your gaming journey.

**Happy Gaming!** 🎯✨

---

*Built with ❤️ for the gaming community*