<?php

// Assumption: $_GET['id'] is always present and an integer
$id = $_GET['id'];
$user = getUserById($id);

// Assumption: $user is never null
echo $user->name;
