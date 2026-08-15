package com.example.demo.service;

import org.springframework.stereotype.Service;
import com.example.demo.repository.UserRepository;

@Service
public class UserService {
    private final UserRepository userRepository;

    public UserService(UserRepository userRepository) {
        this.userRepository = userRepository;
    }

    public String findAll() {
        return userRepository.findAll();
    }
}
