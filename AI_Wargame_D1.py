from __future__ import annotations
import argparse
import copy
from datetime import datetime
from enum import Enum
from dataclasses import dataclass, field
from time import sleep
from typing import Tuple, TypeVar, Type, Iterable, ClassVar
import random
import requests
import signal
import math


# maximum and minimum values for our heuristic scores (usually represents an end of game condition)
MAX_HEURISTIC_SCORE = 2000000000
MIN_HEURISTIC_SCORE = -2000000000

class UnitType(Enum):
    """Every unit type."""
    AI = 0
    Tech = 1
    Virus = 2
    Program = 3
    Firewall = 4

class Player(Enum):
    """The 2 players."""
    Attacker = 0
    Defender = 1

    def next(self) -> Player:
        """The next (other) player."""
        if self is Player.Attacker:
            return Player.Defender
        else:
            return Player.Attacker

class GameType(Enum):
    AttackerVsDefender = 0
    AttackerVsComp = 1
    CompVsDefender = 2
    CompVsComp = 3

##############################################################################################################

@dataclass(slots=True)
class Unit:
    player: Player = Player.Attacker
    type: UnitType = UnitType.Program
    health : int = 9
    # class variable: damage table for units (based on the unit type constants in order)
    damage_table : ClassVar[list[list[int]]] = [
        [3,3,3,3,1], # AI
        [1,1,6,1,1], # Tech
        [9,6,1,6,1], # Virus
        [3,3,3,3,1], # Program
        [1,1,1,1,1], # Firewall
    ]
    # class variable: repair table for units (based on the unit type constants in order)
    repair_table : ClassVar[list[list[int]]] = [
        [0,1,1,0,0], # AI
        [3,0,0,3,3], # Tech
        [0,0,0,0,0], # Virus
        [0,0,0,0,0], # Program
        [0,0,0,0,0], # Firewall
    ]

    def is_alive(self) -> bool:
        """Are we alive ?"""
        return self.health > 0

    def mod_health(self, health_delta : int):
        """Modify this unit's health by delta amount."""
        self.health += health_delta
        if self.health < 0:
            self.health = 0
        elif self.health > 9:
            self.health = 9

    def to_string(self) -> str:
        """Text representation of this unit."""
        p = self.player.name.lower()[0]
        t = self.type.name.upper()[0]
        return f"{p}{t}{self.health}"
    
    def __str__(self) -> str:
        """Text representation of this unit."""
        return self.to_string()
    
    def damage_amount(self, target: Unit) -> int:
        """How much can this unit damage another unit."""
        amount = self.damage_table[self.type.value][target.type.value]
        if target.health - amount < 0:
            return target.health
        return amount

    def repair_amount(self, target: Unit) -> int:
        """How much can this unit repair another unit."""
        amount = self.repair_table[self.type.value][target.type.value]
        if target.health + amount > 9:
            return 9 - target.health
        return amount
    
    def self_destruct(self, coords: Coord):
        "Self destruct"
        

##############################################################################################################

@dataclass(slots=True)
class Coord:
    """Representation of a game cell coordinate (row, col)."""
    row : int = 0
    col : int = 0

    def col_string(self) -> str:
        """Text representation of this Coord's column."""
        coord_char = '?'
        if self.col < 16:
                coord_char = "0123456789abcdef"[self.col]
        return str(coord_char)

    def row_string(self) -> str:
        """Text representation of this Coord's row."""
        coord_char = '?'
        if self.row < 26:
                coord_char = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"[self.row]
        return str(coord_char)

    def to_string(self) -> str:
        """Text representation of this Coord."""
        return self.row_string()+self.col_string()
    
    def __str__(self) -> str:
        """Text representation of this Coord."""
        return self.to_string()
    
    def clone(self) -> Coord:
        """Clone a Coord."""
        return copy.copy(self)

    def iter_range(self, dist: int) -> Iterable[Coord]:
        """Iterates over Coords inside a rectangle centered on our Coord."""
        for row in range(self.row-dist,self.row+1+dist):
            for col in range(self.col-dist,self.col+1+dist):
                yield Coord(row,col)

    def iter_adjacent(self) -> Iterable[Coord]:
        """Iterates over adjacent Coords."""
        yield Coord(self.row-1,self.col)
        yield Coord(self.row,self.col-1)
        yield Coord(self.row+1,self.col)
        yield Coord(self.row,self.col+1)

    @classmethod
    def from_string(cls, s : str) -> Coord | None:
        """Create a Coord from a string. ex: D2."""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 2):
            coord = Coord()
            coord.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coord.col = "0123456789abcdef".find(s[1:2].lower())
            return coord
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class CoordPair:
    """Representation of a game move or a rectangular area via 2 Coords."""
    src : Coord = field(default_factory=Coord)
    dst : Coord = field(default_factory=Coord)

    def to_string(self) -> str:
        """Text representation of a CoordPair."""
        return self.src.to_string()+" "+self.dst.to_string()
    
    def __str__(self) -> str:
        """Text representation of a CoordPair."""
        return self.to_string()

    def clone(self) -> CoordPair:
        """Clones a CoordPair."""
        return copy.copy(self)

    def iter_rectangle(self) -> Iterable[Coord]:
        """Iterates over cells of a rectangular area."""
        for row in range(self.src.row,self.dst.row+1):
            for col in range(self.src.col,self.dst.col+1):
                yield Coord(row,col)

    @classmethod
    def from_quad(cls, row0: int, col0: int, row1: int, col1: int) -> CoordPair:
        """Create a CoordPair from 4 integers."""
        return CoordPair(Coord(row0,col0),Coord(row1,col1))
    
    @classmethod
    def from_dim(cls, dim: int) -> CoordPair:
        """Create a CoordPair based on a dim-sized rectangle."""
        return CoordPair(Coord(0,0),Coord(dim-1,dim-1))
    
    @classmethod
    def from_string(cls, s : str) -> CoordPair | None:
        """Create a CoordPair from a string. ex: A3 B2"""
        s = s.strip()
        for sep in " ,.:;-_":
                s = s.replace(sep, "")
        if (len(s) == 4):
            coords = CoordPair()
            coords.src.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[0:1].upper())
            coords.src.col = "0123456789abcdef".find(s[1:2].lower())
            coords.dst.row = "ABCDEFGHIJKLMNOPQRSTUVWXYZ".find(s[2:3].upper())
            coords.dst.col = "0123456789abcdef".find(s[3:4].lower())
            return coords
        else:
            return None

##############################################################################################################

@dataclass(slots=True)
class Options:
    """Representation of the game options."""
    dim: int = 5
    max_depth : int | None = 4
    min_depth : int | None = 2
    max_time : float | None = 5.0
    game_type : GameType = GameType.AttackerVsDefender
    alpha_beta : bool = True
    max_turns : int | None = 100
    randomize_moves : bool = True
    broker : str | None = None
    heuristic : int | None = 0

##############################################################################################################

@dataclass(slots=True)
class Stats:
    """Representation of the global game statistics."""
    evaluations_per_depth : dict[int,int] = field(default_factory=dict)
    total_seconds: float = 0.0

##############################################################################################################

@dataclass(slots=True)
class Game:
    """Representation of the game state."""
    board: list[list[Unit | None]] = field(default_factory=list)
    next_player: Player = Player.Attacker
    turns_played : int = 0
    options: Options = field(default_factory=Options)
    stats: Stats = field(default_factory=Stats)
    _attacker_has_ai : bool = True
    _defender_has_ai : bool = True

    def __post_init__(self):
        """Automatically called after class init to set up the default board state."""
        dim = self.options.dim
        self.board = [[None for _ in range(dim)] for _ in range(dim)]
        md = dim-1
        self.set(Coord(0,0),Unit(player=Player.Defender,type=UnitType.AI))
        self.set(Coord(1,0),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(0,1),Unit(player=Player.Defender,type=UnitType.Tech))
        self.set(Coord(2,0),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(0,2),Unit(player=Player.Defender,type=UnitType.Firewall))
        self.set(Coord(1,1),Unit(player=Player.Defender,type=UnitType.Program))
        self.set(Coord(md,md),Unit(player=Player.Attacker,type=UnitType.AI))
        self.set(Coord(md-1,md),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md,md-1),Unit(player=Player.Attacker,type=UnitType.Virus))
        self.set(Coord(md-2,md),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md,md-2),Unit(player=Player.Attacker,type=UnitType.Program))
        self.set(Coord(md-1,md-1),Unit(player=Player.Attacker,type=UnitType.Firewall))

    def clone(self) -> Game:
        """Make a new copy of a game for minimax recursion.

        Shallow copy of everything except the board (options and stats are shared).
        """
        new = copy.copy(self)
        new.board = copy.deepcopy(self.board)
        return new

    def is_empty(self, coord : Coord) -> bool:
        """Check if contents of a board cell of the game at Coord is empty (must be valid coord)."""
        return self.board[coord.row][coord.col] is None

    def get(self, coord : Coord) -> Unit | None:
        """Get contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            return self.board[coord.row][coord.col]
        else:
            return None

    def set(self, coord : Coord, unit : Unit | None):
        """Set contents of a board cell of the game at Coord."""
        if self.is_valid_coord(coord):
            self.board[coord.row][coord.col] = unit

    def remove_dead(self, coord: Coord):
        """Remove unit at Coord if dead."""
        unit = self.get(coord)
        if unit is not None and not unit.is_alive():
            self.set(coord,None)
            if unit.type == UnitType.AI:
                if unit.player == Player.Attacker:
                    self._attacker_has_ai = False
                else:
                    self._defender_has_ai = False

    def mod_health(self, coord : Coord, health_delta : int):
        """Modify health of unit at Coord (positive or negative delta)."""
        target = self.get(coord)
        if target is not None:
            target.mod_health(health_delta)
            self.remove_dead(coord)

    def is_valid_move(self, coords : CoordPair) -> bool:
        """Validate a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False
        unit = self.get(coords.src)
        if unit is None or unit.player != self.next_player:
            return False
        if coords.src == coords.dst:
            return True
        adjacent_coords = coords.src.iter_adjacent()
        if coords.dst not in adjacent_coords:
            return False
        target = self.get(coords.dst)
        if target is None:
            if unit.type == UnitType.Tech or unit.type == UnitType.Virus:
                return True
            for coord in adjacent_coords:
                adjacent_unit = self.get(coord)
                if adjacent_unit is not None and adjacent_unit.player != unit.player:
                    return False
            if unit.player == Player.Attacker:
                if coords.dst == Coord(coords.src.row-1, coords.src.col) or coords.dst == Coord(coords.src.row, coords.src.col-1):
                    return True
                else:
                    return False
            else:
                if coords.dst == Coord(coords.src.row+1, coords.src.col) or coords.dst == Coord(coords.src.row, coords.src.col+1):
                    return True
                else:
                    return False
        elif target.player == unit.player and unit.repair_amount(target) > 0:
            return True
        elif target.player != unit.player:
            return True
        else:
            return False
        
    def is_valid_move_for_AI(self, coords : CoordPair, player: Player) -> bool:
        """Validate a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if not self.is_valid_coord(coords.src) or not self.is_valid_coord(coords.dst):
            return False
        unit = self.get(coords.src)
        if unit is None or unit.player != player:
            return False
        if coords.src == coords.dst:
            return True
        adjacent_coords = coords.src.iter_adjacent()
        target = self.get(coords.dst)
        if target is None:
            if unit.type == UnitType.Tech or unit.type == UnitType.Virus:
                return True
            for coord in adjacent_coords:
                adjacent_unit = self.get(coord)
                if adjacent_unit is not None and adjacent_unit.player != unit.player:
                    return False
            if unit.player == Player.Attacker:
                if coords.dst == Coord(coords.src.row-1, coords.src.col) or coords.dst == Coord(coords.src.row, coords.src.col-1):
                    return True
                else:
                    return False
            else:
                if coords.dst == Coord(coords.src.row+1, coords.src.col) or coords.dst == Coord(coords.src.row, coords.src.col+1):
                    return True
                else:
                    return False
        elif target.player == unit.player and unit.repair_amount(target) > 0:
            return True
        elif target.player != unit.player:
            return True
        else:
            return False


        # if unit.type == UnitType.Tech or unit.type == UnitType.AI:
        #     if target is None:
        #         return True
        #     elif target.player == unit.player and unit.repair_amount(target) > 0:
        #         return True
        #     elif target.player != unit.player:
        #         return True
        # if unit.type == UnitType.Virus:
        #     if target is None:
        #         return True
        #     if target.player != unit.player:
        #         return True
        # if self.next_player.name
        return True

    def perform_move(self, coords : CoordPair) -> Tuple[bool,str]:
        """Validate and perform a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        if self.is_valid_move(coords):
            return_str = ""
            dst_unit = self.get(coords.dst)
            src_unit = self.get(coords.src)
            if dst_unit is None:
                self.set(coords.dst,src_unit)
                self.set(coords.src,None)
                return_str = self.next_player.name + " has moved " + coords.src.to_string() + " to " + coords.dst.to_string()
            elif coords.dst == coords.src:
                src_unit.mod_health(-src_unit.health)
                self.remove_dead(coords.src)
                units_in_range = coords.src.iter_range(1)
                for unit_in_range in units_in_range:
                    if unit_in_range is not None:
                        self.mod_health(unit_in_range, -2)
                return_str = self.next_player.name + " has self destructed unit " + coords.src.to_string()
            elif dst_unit.player is self.next_player:
                dst_unit.mod_health(src_unit.repair_amount(dst_unit))
                return_str = self.next_player.name + " has moved " + coords.src.to_string() + " to repair " + coords.dst.to_string()
            elif dst_unit.player is not self.next_player:
                dst_unit.mod_health(-src_unit.damage_amount(dst_unit))
                src_unit.mod_health(-dst_unit.damage_amount(src_unit))
                self.remove_dead(coords.dst)
                self.remove_dead(coords.src)
                return_str = self.next_player.name + " has moved " + coords.src.to_string() + " to damage " + coords.dst.to_string()
            print(return_str)
            return (True, return_str)
        return (False,"Invalid move " + coords.src.to_string() + " to " + coords.dst.to_string())
    
    def perform_move_for_AI(self, coords : CoordPair, player: Player) -> Tuple[bool,str]:
        """Validate and perform a move expressed as a CoordPair. TODO: WRITE MISSING CODE!!!"""
        return_str = ""
        dst_unit = self.get(coords.dst)
        src_unit = self.get(coords.src)
        if dst_unit is None:
            self.set(coords.dst,src_unit)
            self.set(coords.src,None)
            return_str = player.name + " has moved " + coords.src.to_string() + " to " + coords.dst.to_string()
        elif coords.dst == coords.src:
            src_unit.mod_health(-src_unit.health)
            self.remove_dead(coords.src)
            units_in_range = coords.src.iter_range(1)
            for unit_in_range in units_in_range:
                if unit_in_range is not None:
                    self.mod_health(unit_in_range, -2)
            return_str = player.name + " has self destructed unit " + coords.src.to_string()
        elif dst_unit.player is player:
            dst_unit.mod_health(src_unit.repair_amount(dst_unit))
            return_str = player.name + " has moved " + coords.src.to_string() + " to repair " + coords.dst.to_string()
        elif dst_unit.player is not player:
            dst_unit.mod_health(-src_unit.damage_amount(dst_unit))
            src_unit.mod_health(-dst_unit.damage_amount(src_unit))
            self.remove_dead(coords.dst)
            self.remove_dead(coords.src)
            return_str = player.name + " has moved " + coords.src.to_string() + " to damage " + coords.dst.to_string()
        return (True, return_str)

    def next_turn(self):
        """Transitions game to the next turn."""
        self.next_player = self.next_player.next()
        self.turns_played += 1

    def to_string(self) -> str:
        """Pretty text representation of the game."""
        dim = self.options.dim
        output = ""
        output += f"Next player: {self.next_player.name}\n"
        output += f"Turns played: {self.turns_played}\n"
        coord = Coord()
        output += "\n   "
        for col in range(dim):
            coord.col = col
            label = coord.col_string()
            output += f"{label:^3} "
        output += "\n"
        for row in range(dim):
            coord.row = row
            label = coord.row_string()
            output += f"{label}: "
            for col in range(dim):
                coord.col = col
                unit = self.get(coord)
                if unit is None:
                    output += " .  "
                else:
                    output += f"{str(unit):^3} "
            output += "\n"
        return output

    def __str__(self) -> str:
        """Default string representation of a game."""
        return self.to_string()
    
    def is_valid_coord(self, coord: Coord) -> bool:
        """Check if a Coord is valid within out board dimensions."""
        dim = self.options.dim
        if coord.row < 0 or coord.row >= dim or coord.col < 0 or coord.col >= dim:
            return False
        return True

    def read_move(self) -> CoordPair:
        """Read a move from keyboard and return as a CoordPair."""
        while True:
            s = input(F'Player {self.next_player.name}, enter your move: ')
            coords = CoordPair.from_string(s)
            if coords is not None and self.is_valid_coord(coords.src) and self.is_valid_coord(coords.dst):
                return coords
            else:
                print('Invalid coordinates! Try again.')
    
    def human_turn(self) -> str:
        """Human player plays a move (or get via broker)."""
        if self.options.broker is not None:
            print("Getting next move with auto-retry from game broker...")
            while True:
                mv = self.get_move_from_broker()
                if mv is not None:
                    (success,result) = self.perform_move(mv)
                    print(f"Broker {self.next_player.name}: ",end='')
                    print(result)
                    self.next_turn()
                    return result
                sleep(0.1)
        else:
            while True:
                mv = self.read_move()
                (success,result) = self.perform_move(mv)
                if success:
                    print(f"Player {self.next_player.name}: ",end='')
                    print(result)
                    self.next_turn()
                else:
                    print("The move is not valid! Try again.")
                return result

    def computer_turn(self) -> Tuple[CoordPair | None, str]:
        """Computer plays a move."""
        mv, return_string = self.suggest_move()
        if mv is not None:
            (success,result) = self.perform_move_for_AI(mv, self.next_player)
            if success:
                print(f"Computer {result}")
                return_string += f"\n\nComputer {result}"
                self.next_turn()
        return (mv, return_string)

    def player_units(self, player: Player) -> Iterable[Tuple[Coord,Unit]]:
        """Iterates over all units belonging to a player."""
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
            unit = self.get(coord)
            if unit is not None and unit.player == player:
                yield (coord,unit)

    def is_finished(self) -> bool:
        """Check if the game is over."""
        return self.has_winner() is not None

    def has_winner(self) -> Player | None:
        """Check if the game is over and returns winner"""
        if self.options.max_turns is not None and self.turns_played >= self.options.max_turns:
            return Player.Defender
        if self._attacker_has_ai:
            if self._defender_has_ai:
                return None
            else:
                return Player.Attacker    
        return Player.Defender

    def move_candidates(self) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        # if self.has_winner() is not None:
        #     return iter([])
        move = CoordPair()
        for (src,_) in self.player_units(self.next_player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move(move):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def move_candidates_for_AI(self, player: Player) -> Iterable[CoordPair]:
        """Generate valid move candidates for the next player."""
        if self.has_winner() is not None:
            return iter([])
        move = CoordPair()
        for (src,_) in self.player_units(player):
            move.src = src
            for dst in src.iter_adjacent():
                move.dst = dst
                if self.is_valid_move_for_AI(move, player):
                    yield move.clone()
            move.dst = src
            yield move.clone()

    def random_move(self) -> Tuple[int, CoordPair | None, float]:
        """Returns a random move."""
        move_candidates = list(self.move_candidates())
        random.shuffle(move_candidates)
        if len(move_candidates) > 0:
            return (0, move_candidates[0], 1)
        else:
            return (0, None, 0)
    
    def compute_heuristic_e0(self) -> int:
        heuristic_score = 0
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
                unit = self.get(coord)
                if unit is not None and unit.player == Player.Attacker:
                    if (unit.type == UnitType.AI):
                        heuristic_score = heuristic_score + 9999
                    else:
                        heuristic_score = heuristic_score + 3
                elif unit is not None and unit.player == Player.Defender:
                    if (unit.type == UnitType.AI):
                        heuristic_score = heuristic_score - 9999
                    else:
                        heuristic_score = heuristic_score - 3
        return heuristic_score
    
    def compute_heuristic_e1(self) -> int:
        heuristic_score = 0
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
                unit = self.get(coord)
                if unit is not None and unit.player == Player.Attacker:
                    if (unit.type == UnitType.AI):
                        heuristic_score = heuristic_score + 999*(unit.health/9)
                    elif (unit.type == UnitType.Virus):
                        heuristic_score = heuristic_score + 9*(unit.health/9)
                    elif (unit.type == UnitType.Program):
                        heuristic_score = heuristic_score + 7*(unit.health/9)
                    else:
                        heuristic_score = heuristic_score + 3*(unit.health/9)
                elif unit is not None and unit.player == Player.Defender:
                    if (unit.type == UnitType.AI):
                        heuristic_score = heuristic_score - 999*(unit.health/9)
                    elif (unit.type == UnitType.Tech):
                        heuristic_score = heuristic_score - 8*(unit.health/9)
                    elif (unit.type == UnitType.Program):
                        heuristic_score = heuristic_score - 8*(unit.health/9)
                    else:
                        heuristic_score = heuristic_score - 3*(unit.health/9)
        return heuristic_score
    
    def compute_heuristic_e2(self) -> int:
        heuristic_score = 0
        Attacker_AI_coord = None
        Defender_AI_coord = None
        Virus_coord_1 = None
        Virus_coord_2 = None
        Tech_coord_1 = None
        Tech_coord_2 = None
        for coord in CoordPair.from_dim(self.options.dim).iter_rectangle():
                unit = self.get(coord)
                if unit is not None and unit.player == Player.Attacker:
                    if (unit.type == UnitType.AI):
                        heuristic_score = heuristic_score + 999*(unit.health/9)
                        Attacker_AI_coord = coord
                        adjacent_units = 0
                        for coord_around in coord.iter_adjacent():
                            unit_around = self.get(coord_around)
                            if unit_around is not None and unit_around.player == unit.player:
                                adjacent_units = adjacent_units + 1
                                heuristic_score = heuristic_score + 3*(9/unit.health)
                                if(adjacent_units == 4):
                                    heuristic_score = heuristic_score + 5
                    elif (unit.type == UnitType.Virus):
                        heuristic_score = heuristic_score + 9*(unit.health/9)
                        if(Virus_coord_1 is not None):
                            Virus_coord_2 = coord
                        else:
                            Virus_coord_1 = coord
                    elif (unit.type == UnitType.Program):
                        heuristic_score = heuristic_score + 7*(unit.health/9)
                    else:
                        heuristic_score = heuristic_score + 3*(unit.health/9)
                elif unit is not None and unit.player == Player.Defender:
                    if (unit.type == UnitType.AI):
                        heuristic_score = heuristic_score - 999*(unit.health/9)
                        Defender_AI_coord = coord
                        adjacent_units = 0
                        for coord_around in coord.iter_adjacent():
                            unit_around = self.get(coord_around)
                            if unit_around is not None and unit_around.player == unit.player:
                                adjacent_units = adjacent_units + 1
                                heuristic_score = heuristic_score - 40
                                if(adjacent_units == 2):
                                    heuristic_score = heuristic_score - 50
                    elif (unit.type == UnitType.Tech):
                        heuristic_score = heuristic_score - 50*(unit.health/9)
                        if(Tech_coord_1 is not None):
                            Tech_coord_2 = coord
                        else:
                            Tech_coord_1 = coord
                    elif (unit.type == UnitType.Program):
                        heuristic_score = heuristic_score - 40*(unit.health/9)
                    else:
                        heuristic_score = heuristic_score - 40*(unit.health/9)
        if ((Virus_coord_1 is not None and Virus_coord_2 is not None) and Defender_AI_coord is not None):
            heuristic_score = heuristic_score + 100/max((abs(Virus_coord_1.row - Defender_AI_coord.row) + abs(Virus_coord_1.col - Defender_AI_coord.col)), (abs(Virus_coord_2.row-Defender_AI_coord.row) + abs(Virus_coord_2.col - Defender_AI_coord.col)))
        if ((Virus_coord_1 is not None or Virus_coord_2 is not None) and Defender_AI_coord is not None):
            Virus_coord = Virus_coord_1 if Virus_coord_2 is None else Virus_coord_2
            heuristic_score = heuristic_score + 100/(abs(Virus_coord.row - Defender_AI_coord.row) + abs(Virus_coord.col - Defender_AI_coord.col)) - 9
        if ((Tech_coord_1 is not None and Tech_coord_2 is not None) and Attacker_AI_coord is not None):
            heuristic_score = heuristic_score - 50/max((abs(Tech_coord_1.row-Attacker_AI_coord.row) + abs(Tech_coord_1.col - Attacker_AI_coord.col)), (abs(Tech_coord_2.row-Attacker_AI_coord.row) + abs(Tech_coord_2.col - Attacker_AI_coord.col)))
        if ((Tech_coord_1 is not None or Tech_coord_2 is not None) and Attacker_AI_coord is not None):
            Tech_coord = Tech_coord_1 if Tech_coord_2 is None else Tech_coord_2
            heuristic_score = heuristic_score - 50/(abs(Tech_coord.row-Attacker_AI_coord.row) + abs(Tech_coord.col - Attacker_AI_coord.col)) + 9
        return heuristic_score
    
    def run_algorithm(self, player: Player, start_time: datetime) -> Tuple[int, CoordPair]:
        """Returns a minimax move."""
        if(self.options.alpha_beta == False):
            return self.minimax(1, player, start_time)
        else:
            return self.minimax_alphabeta(1, player, MIN_HEURISTIC_SCORE, MAX_HEURISTIC_SCORE, start_time)
    
    def minimax(self, depth: int, player: Player, start_time: datetime) -> Tuple[int, CoordPair]:
        """Returns a minimax move."""
        if (depth==self.options.max_depth or self.has_winner() is not None):
            if (self.options.heuristic == 0):
                return (self.compute_heuristic_e0(), None)
            elif (self.options.heuristic == 1):
                print(self.compute_heuristic_e1())
                return (self.compute_heuristic_e1(), None)
            else:
                return (self.compute_heuristic_e2(), None)
        move_candidates = list(self.move_candidates_for_AI(player))
        best_heuristic = MAX_HEURISTIC_SCORE if player == Player.Defender else MIN_HEURISTIC_SCORE
        best_move = None
        best_clone_game = None
        self.stats.evaluations_per_depth[depth] = self.stats.evaluations_per_depth.get(depth, 0) + len(move_candidates)
        if len(move_candidates) > 0:
            for move_candidate in move_candidates:
                clone_game = self.clone()
                # print(player.name + " will perform move " + str(move_candidate) + " at depth " + str(depth))
                clone_game.perform_move_for_AI(move_candidate, player)
                current_heuristic,_ = clone_game.minimax(depth+1, Player.Attacker if player == Player.Defender else Player.Defender, start_time)
                # print(str(self.player_units(player)))
                # print(player.name + " just came back from analyzing " + str(move_candidate) + " and got " + str(current_heuristic) + " at a depth " + str(depth))
                if (player == Player.Attacker and current_heuristic > best_heuristic) or (player == Player.Defender and current_heuristic < best_heuristic):
                    best_heuristic = current_heuristic
                    best_move = move_candidate
                    best_clone_game = clone_game

                if (datetime.now() - start_time).total_seconds() >= (self.options.max_time-0.1):
                    break
                # else:
                #     print(str(best_heuristic) + " BIG " + str(current_move[0]))
            # print(player.name + " chose to perform move " + str(best_move) + " for a heuristic of " + str(best_heuristic))
            if(self.options.heuristic == 0):
                return (best_clone_game.compute_heuristic_e0(), best_move)
            elif(self.options.heuristic == 1):
                return (best_clone_game.compute_heuristic_e1(), best_move)
            else:
                return (best_clone_game.compute_heuristic_e2(), best_move)
        
    def minimax_alphabeta(self, depth: int, player: Player, alpha: int, beta: int, start_time: datetime) -> Tuple[int, CoordPair]:
        """Returns a minimax alpha-beta move."""
        if (depth==self.options.max_depth or self.has_winner() is not None):
            if (self.options.heuristic == 0):
                return (self.compute_heuristic_e0(), None)
            elif (self.options.heuristic == 1):
                return (self.compute_heuristic_e1(), None)
            else:
                return (self.compute_heuristic_e2(), None)
        move_candidates = list(self.move_candidates_for_AI(player))
        best_heuristic = MAX_HEURISTIC_SCORE if player == Player.Defender else MIN_HEURISTIC_SCORE
        best_move = None
        best_clone_game = None
        self.stats.evaluations_per_depth[depth] = self.stats.evaluations_per_depth.get(depth, 0) + len(move_candidates)
        if len(move_candidates) > 0:
            for move_candidate in move_candidates:
                clone_game = self.clone()
                clone_game.perform_move_for_AI(move_candidate, player)
                current_heuristic,_ = clone_game.minimax_alphabeta(depth+1, Player.Attacker if player==Player.Defender else Player.Defender, alpha, beta, start_time)
                if (player == Player.Attacker):
                    if (current_heuristic > best_heuristic):
                        best_heuristic = current_heuristic
                        best_move = move_candidate
                        best_clone_game = clone_game
                    alpha = max(alpha, best_heuristic)
                    if (beta <= alpha):
                        break
                if (player == Player.Defender):
                    if (current_heuristic < best_heuristic):
                        best_heuristic = current_heuristic
                        best_move = move_candidate
                        best_clone_game = clone_game
                    beta = min(beta, best_heuristic)
                    if (beta <= alpha):
                        break
                if (datetime.now() - start_time).total_seconds() >= (self.options.max_time-0.1):
                    break
            # if(depth == 0):
            #     print(player.name + " chose to play move " + str(best_move) + " with heuristic " + str(best_heuristic))
            
            if(self.options.heuristic == 0):
                return (best_clone_game.compute_heuristic_e0(), best_move)
            elif(self.options.heuristic == 1):
                return (best_clone_game.compute_heuristic_e1(), best_move)
            else:
                return (best_clone_game.compute_heuristic_e2(), best_move)
        
    def suggest_move(self) -> Tuple[CoordPair | None, str]:
        """Suggest the next move using minimax alpha beta. TODO: REPLACE RANDOM_MOVE WITH PROPER GAME LOGIC!!!"""
        start_time = datetime.now()
        (score, move) = self.run_algorithm(self.next_player, start_time)
        elapsed_seconds = (datetime.now() - start_time).total_seconds()
        if (elapsed_seconds > self.options.max_time):
            for coord,unit in self.player_units(self.next_player):
                if unit.type == UnitType.AI:
                    unit.mod_health(-unit.health)
                    return (None, "Computer timed out!")
        self.stats.total_seconds += elapsed_seconds
        return_str = f"Heuristic score: {score}\n\nEvals per depth: "
        print(f"Heuristic score: {score}")
        print(f"Evals per depth: ",end='')
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]} ",end='')
            return_str += f"{k}:{self.stats.evaluations_per_depth[k]} "
        return_str += "\n\n"
        print()
        print(f"Percent evals per depth: ",end='')
        return_str += f"Percent evals per depth: "
        total_evals = sum(self.stats.evaluations_per_depth.values())
        for k in sorted(self.stats.evaluations_per_depth.keys()):
            print(f"{k}:{self.stats.evaluations_per_depth[k]/total_evals} ",end='')
            return_str += f"{k}:{self.stats.evaluations_per_depth[k]/total_evals} "
        return_str += "\n\n"
        return_str += f"Cumulative evals: {total_evals}\n\n"
        print()
        if self.stats.total_seconds > 0:
            print(f"Eval perf.: {total_evals/self.stats.total_seconds/1000:0.1f}k/s")
            return_str += f"Eval perf.: {total_evals/self.stats.total_seconds/1000:0.1f}k/s"
        print(f"Elapsed time: {elapsed_seconds:0.1f}s")
        return_str += f"\n\nElapsed time: {elapsed_seconds:0.1f}s"
        return move, return_str

    def post_move_to_broker(self, move: CoordPair):
        """Send a move to the game broker."""
        if self.options.broker is None:
            return
        data = {
            "from": {"row": move.src.row, "col": move.src.col},
            "to": {"row": move.dst.row, "col": move.dst.col},
            "turn": self.turns_played
        }
        try:
            r = requests.post(self.options.broker, json=data)
            if r.status_code == 200 and r.json()['success'] and r.json()['data'] == data:
                # print(f"Sent move to broker: {move}")
                pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")

    def get_move_from_broker(self) -> CoordPair | None:
        """Get a move from the game broker."""
        if self.options.broker is None:
            return None
        headers = {'Accept': 'application/json'}
        try:
            r = requests.get(self.options.broker, headers=headers)
            if r.status_code == 200 and r.json()['success']:
                data = r.json()['data']
                if data is not None:
                    if data['turn'] == self.turns_played+1:
                        move = CoordPair(
                            Coord(data['from']['row'],data['from']['col']),
                            Coord(data['to']['row'],data['to']['col'])
                        )
                        print(f"Got move from broker: {move}")
                        return move
                    else:
                        # print("Got broker data for wrong turn.")
                        # print(f"Wanted {self.turns_played+1}, got {data['turn']}")
                        pass
                else:
                    # print("Got no data from broker")
                    pass
            else:
                print(f"Broker error: status code: {r.status_code}, response: {r.json()}")
        except Exception as error:
            print(f"Broker error: {error}")
        return None

##############################################################################################################

def main():
    file_output = ""
    # parse command line arguments
    parser = argparse.ArgumentParser(
        prog='ai_wargame',
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('--max_depth', type=int, help='maximum search depth')
    parser.add_argument('--max_time', type=float, help='maximum search time')
    parser.add_argument('--game_type', type=str, default="auto", help='game type: auto|attacker|defender|manual')
    parser.add_argument('--broker', type=str, help='play via a game broker')
    parser.add_argument('--max_turns', type=int, help='set limit number of turns')
    parser.add_argument('--alpha_beta', action="store_true", help='set alpha-beta as true')
    parser.add_argument('--heuristic', type=int, help='set 0 for e0, 1 for e1...', default=0)
    args = parser.parse_args()

    # parse the game type
    if args.game_type == "attacker":
        game_type = GameType.AttackerVsComp
        file_output += "Player 1: Human\nPlayer 2: AI\nAlpha-Beta: " + str(args.alpha_beta) + "\n\n" + "Heuristic used: " + str(args.heuristic) + "\n\n"
    elif args.game_type == "defender":
        game_type = GameType.CompVsDefender
        file_output += "Player 1: AI \nPlayer 2: Human\nAlpha-Beta: " + str(args.alpha_beta) + "\n\n" + "Heuristic used: " + str(args.heuristic) + "\n\n"
    elif args.game_type == "manual":
        game_type = GameType.AttackerVsDefender
        file_output += "Player 1: Human \nPlayer 2: Human\n\n"
    else:
        game_type = GameType.CompVsComp
        file_output += "Player 1: AI \nPlayer 2: AI\nAlpha-Beta: " + str(args.alpha_beta) + "\n\n" + "Heuristic used: " + str(args.heuristic) + "\n\n"

    # set up game options
    options = Options(game_type=game_type)

    options.heuristic = args.heuristic

    # override class defaults via command line options
    
    file_output += "Max turns: " + str(args.max_turns) + "\n\n"
    if args.max_depth is not None:
        options.max_depth = args.max_depth
    if args.max_time is not None:
        options.max_time = args.max_time
        file_output += "Timeout time: " + str(args.max_time) + " seconds\n\n"
    else:
        file_output += "Timeout time: None\n\n"
    if args.broker is not None:
        options.broker = args.broker
    if args.max_turns is not None:
        options.max_turns = args.max_turns
    if args.alpha_beta is not None:
        options.alpha_beta = args.alpha_beta

    # create a new game
    game = Game(options=options)

    # the main game loop
    while True:
        file_output += game.to_string() + "\n"
        print(game)
        winner = game.has_winner()
        if winner is not None:
            file_output += winner.name + " wins in " + str(game.turns_played) + " turns"
            print(f"{winner.name} wins!")
            f = open("gameTrace-{}-{}-{}.txt".format(args.alpha_beta, args.max_time, args.max_turns), "w")
            f.write(file_output)
            f.close()
            break
        if game.options.game_type == GameType.AttackerVsDefender:
            move = game.human_turn()
            file_output += move + "\n\n"
        elif game.options.game_type == GameType.AttackerVsComp and game.next_player == Player.Attacker:
            move = game.human_turn()
            file_output += move + "\n\n"
        elif game.options.game_type == GameType.CompVsDefender and game.next_player == Player.Defender:
            move = game.human_turn()
            file_output += move + "\n\n"
        else:
            player = game.next_player
            (move, result) = game.computer_turn()
            if move is not None:
                file_output += result + "\n\n"
                game.post_move_to_broker(move)
            else:
                print("Computer doesn't know what to do!!!")

##############################################################################################################

if __name__ == '__main__':
    main()
