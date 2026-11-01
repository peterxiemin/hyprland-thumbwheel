CXX ?= g++
CXXFLAGS := -std=c++23 -O2 -Wall -Wextra -Wno-unused-parameter -fPIC
TARGET := thumbwheel.so

.PHONY: all
all: $(TARGET)

$(TARGET): main.cpp
	$(CXX) $(CXXFLAGS) -shared $< -o $@.new $$(pkg-config --cflags --libs hyprland libeis-1.0)
	mv $@.new $@

.PHONY: clean
clean:
	$(RM) $(TARGET)
