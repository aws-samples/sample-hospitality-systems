import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react';
import * as bookingService from '@/services/bookingService';

export interface CartProperty {
  propertyId: string;
  name: string;
  city: string;
  country: string;
  imageUrl: string;
}

export interface CartRoomType {
  roomTypeId: string;
  name: string;
  description: string;
  maxOccupancy: number;
  imageUrl: string;
}

export interface CartRatePlan {
  ratePlanId: string;
  name: string;
  code: string;
  cancellationPolicy: string;
}

export interface CartGuests {
  adults: number;
  children: number;
}

export interface CartPricing {
  nightlyRate: number;
  numberOfNights: number;
  subtotal: number;
  taxes: number;
  fees: number;
  total: number;
  currency: string;
}

export interface Cart {
  cartId: string;
  property: CartProperty;
  roomType: CartRoomType;
  ratePlan: CartRatePlan;
  dates: {
    checkIn: string;
    checkOut: string;
  };
  guests: CartGuests;
  pricing: CartPricing;
  promoCode: string | null;
  discountAmount: number;
}

export interface CreateCartParams {
  propertyId: string;
  roomTypeId: string;
  ratePlanId: string;
  checkIn: string;
  checkOut: string;
  adults: number;
  children: number;
}

export interface UpdateCartParams {
  roomTypeId?: string;
  ratePlanId?: string;
  checkIn?: string;
  checkOut?: string;
  adults?: number;
  children?: number;
}

interface CartContextType {
  cart: Cart | null;
  isLoading: boolean;
  createCart: (params: CreateCartParams) => Promise<Cart>;
  updateCart: (cartId: string, params: UpdateCartParams) => Promise<Cart>;
  applyPromo: (cartId: string, code: string) => Promise<Cart>;
  clearCart: () => void;
}

const CART_STORAGE_KEY = 'anycompany_booking_cart';

const CartContext = createContext<CartContextType | undefined>(undefined);

function loadCartFromStorage(): Cart | null {
  try {
    const stored = sessionStorage.getItem(CART_STORAGE_KEY);
    if (stored) {
      return JSON.parse(stored) as Cart;
    }
  } catch {
    sessionStorage.removeItem(CART_STORAGE_KEY);
  }
  return null;
}

function saveCartToStorage(cart: Cart | null): void {
  if (cart) {
    sessionStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
  } else {
    sessionStorage.removeItem(CART_STORAGE_KEY);
  }
}

export function CartProvider({ children }: { children: ReactNode }) {
  const [cart, setCart] = useState<Cart | null>(() => loadCartFromStorage());
  const [isLoading, setIsLoading] = useState(false);

  // Sync cart to sessionStorage whenever it changes
  useEffect(() => {
    saveCartToStorage(cart);
  }, [cart]);

  const createCart = useCallback(async (params: CreateCartParams): Promise<Cart> => {
    setIsLoading(true);
    try {
      const response = await bookingService.createCart({
        ...params,
        sessionId: crypto.randomUUID(),
      } as any);
      const newCart = response as Cart;
      setCart(newCart);
      return newCart;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const updateCart = useCallback(async (cartId: string, params: UpdateCartParams): Promise<Cart> => {
    setIsLoading(true);
    try {
      const response = await bookingService.updateCart(cartId, params);
      const updatedCart = response as Cart;
      setCart(updatedCart);
      return updatedCart;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const applyPromo = useCallback(async (cartId: string, code: string): Promise<Cart> => {
    setIsLoading(true);
    try {
      const response = await bookingService.applyPromo(cartId, code);
      const updatedCart = response as Cart;
      setCart(updatedCart);
      return updatedCart;
    } finally {
      setIsLoading(false);
    }
  }, []);

  const clearCart = useCallback(() => {
    setCart(null);
    sessionStorage.removeItem(CART_STORAGE_KEY);
  }, []);

  const value: CartContextType = {
    cart,
    isLoading,
    createCart,
    updateCart,
    applyPromo,
    clearCart,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartContextType {
  const context = useContext(CartContext);
  if (context === undefined) {
    throw new Error('useCart must be used within a CartProvider');
  }
  return context;
}
